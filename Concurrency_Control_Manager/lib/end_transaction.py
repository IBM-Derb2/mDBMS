from typing import List, Dict, Any
from dataclasses import dataclass, field
from .transaction_model import TransactionManager, TransactionStatus
from .strategy_interface import ConcurrencyStrategy


@dataclass
class EndTransactionReport:
    """Result report for end transaction operation."""

    transaction_id: int
    success: bool = False
    messages: List[str] = field(default_factory=list)

    def add_message(self, message: str):
        self.messages.append(message)

    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"
        msg_text = "\n".join(f"  - {msg}" for msg in self.messages)
        return f"End Transaction TX {self.transaction_id}: {status}\n{msg_text}"


class EndTransactionManager:
    def __init__(self, tx_manager: TransactionManager, strategy: ConcurrencyStrategy):
        self.tx_manager = tx_manager
        self.strategy = strategy
        self.undo_log_manager = None  # Will be set by ConcurrencyControlManager

    def end_transaction(
        self, transaction_id: int, is_commit: bool = True
    ) -> EndTransactionReport:
        """Execute end transaction with undo log support."""
        # Initialize report first
        report = EndTransactionReport(transaction_id=transaction_id)

        try:
            # Validate transaction exists and is active
            tx = self.tx_manager.get_transaction(transaction_id)
            if not tx:
                report.success = False
                report.add_message(f"Transaction {transaction_id} not found")
                return report

            if tx.status != TransactionStatus.ACTIVE:
                report.success = False
                report.add_message(
                    f"Transaction {transaction_id} is not active (status: {tx.status.value})"
                )
                return report

            # Perform rollback if aborting
            if not is_commit and self.undo_log_manager:
                rolled_back = self.undo_log_manager.rollback_transaction(
                    transaction_id)
                if rolled_back:  # Check if list is not None/empty
                    report.add_message(
                        f"Rolled back {len(rolled_back)} operations for TX {transaction_id}"
                    )
                else:
                    report.add_message(
                        f"No operations to rollback for TX {transaction_id}"
                    )

            # Clean up undo logs after commit or abort
            if self.undo_log_manager:
                self.undo_log_manager.clear_transaction(transaction_id)

            # Release locks
            self.strategy.end_transaction(transaction_id)
            report.add_message(f"Released locks for TX {transaction_id}")

            # Update transaction status
            if is_commit:
                self.tx_manager.commit_transaction(transaction_id)
                report.add_message(
                    f"Transaction {transaction_id} committed successfully"
                )
            else:
                self.tx_manager.abort_transaction(transaction_id)
                report.add_message(f"Transaction {transaction_id} aborted")

            # Mark as terminated
            self.tx_manager.terminate_transaction(transaction_id)
            report.success = True

        except Exception as e:
            report.success = False
            report.add_message(f"Error during end transaction: {str(e)}")
            import traceback

            traceback.print_exc()

        return report

    def _validation_needed_for_strategy(self) -> bool:
        strategy_name = self.strategy.__class__.__name__
        return strategy_name == "ValidationBasedStrategy"

    def _perform_final_validation(self, transaction_id: int) -> Dict[str, Any]:
        errors = []
        valid = True

        tx = self.tx_manager.get_transaction(transaction_id)
        if not tx:
            return {"valid": False, "errors": ["Transaction not found"]}

        # Cek konflik dengan transaksi lain yang sudah commit
        for other_tx_id in self.tx_manager.committed_transactions:
            if other_tx_id == transaction_id:
                continue

            other_tx = self.tx_manager.get_transaction(other_tx_id)
            if not other_tx:
                continue

            # Cek write-read conflict
            write_read_conflict = tx.write_set.intersection(other_tx.read_set)
            if write_read_conflict:
                errors.append(
                    f"Write-Read conflict dengan TX {other_tx_id} "
                    f"pada objek: {write_read_conflict}"
                )
                valid = False

            # Cek write-write conflict
            write_write_conflict = tx.write_set.intersection(
                other_tx.write_set)
            if write_write_conflict:
                errors.append(
                    f"Write-Write conflict dengan TX {other_tx_id} "
                    f"pada objek: {write_write_conflict}"
                )
                valid = False

        return {"valid": valid, "errors": errors}

    def _perform_validation(self, transaction_id: int) -> Dict[str, Any]:
        """Perform validation if strategy requires it."""
        # Check if strategy has validation method
        if hasattr(self.strategy, "validate_for_commit"):
            is_valid, errors = self.strategy.validate_for_commit(
                transaction_id)
            return {"valid": is_valid, "errors": errors}

        # Default validation - check conflicts with committed transactions
        return self._perform_final_validation(transaction_id)
