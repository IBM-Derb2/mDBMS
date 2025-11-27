from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from .undo_log import UndoLogManager
from .transaction_model import TransactionStatus


class EndTransactionResult(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    VALIDATION_FAILED = "validation_failed"
    RESOURCE_CLEANUP_FAILED = "resource_cleanup_failed"


@dataclass
class EndTransactionReport:
    transaction_id: int
    result: EndTransactionResult
    timestamp: datetime
    locks_released: List[str]
    resources_cleaned: List[str]
    validation_errors: List[str]
    execution_time_ms: float

    def __repr__(self):
        return (
            f"EndTxReport(TX={self.transaction_id}, "
            f"Result={self.result.value}, "
            f"Locks Released={len(self.locks_released)}, "
            f"Time={self.execution_time_ms:.2f}ms)"
        )


class EndTransactionManager:

    def __init__(
        self, tx_manager, strategy, undo_log_manager: Optional[UndoLogManager] = None
    ):
        self.tx_manager = tx_manager
        self.strategy = strategy
        self.undo_log_manager = (
            undo_log_manager if undo_log_manager else UndoLogManager()
        )
        self.end_transaction_history: List[EndTransactionReport] = []

    def end_transaction(
        self, transaction_id: int, is_commit: bool = True
    ) -> EndTransactionReport:
        start_time = datetime.now()
        locks_released = []
        resources_cleaned = []
        validation_errors = []
        result = EndTransactionResult.SUCCESS

        try:
            tx = self.tx_manager.get_transaction(transaction_id)
            if not tx:
                validation_errors.append(f"Transaction {transaction_id} not found")
                result = EndTransactionResult.VALIDATION_FAILED
                raise ValueError(f"Transaction {transaction_id} not found")

            if is_commit:
                if self._validation_needed_for_strategy():
                    if hasattr(self.strategy, "validate_for_commit"):
                        is_valid, strategy_errors = self.strategy.validate_for_commit(
                            transaction_id
                        )
                        if not is_valid:
                            validation_errors.extend(strategy_errors)
                            result = EndTransactionResult.VALIDATION_FAILED
                            is_commit = False
                    else:
                        validation_result = self._perform_final_validation(
                            transaction_id
                        )
                        if not validation_result["valid"]:
                            validation_errors.extend(validation_result["errors"])
                            result = EndTransactionResult.VALIDATION_FAILED
                            is_commit = False

            accessed_objects = tx.get_accessed_objects()
            locks_released = self._release_resources_list(
                transaction_id, accessed_objects
            )

            if is_commit and result == EndTransactionResult.SUCCESS:
                self.tx_manager.commit_transaction(transaction_id)
                resources_cleaned.append(f"Transaction {transaction_id} committed")

                if hasattr(self.strategy, "commit_validation"):
                    self.strategy.commit_validation(transaction_id)

                self.undo_log_manager.commit_transaction(transaction_id)
                resources_cleaned.append(f"Undo logs cleared for TX {transaction_id}")
            else:
                if self.undo_log_manager.has_logs(transaction_id):
                    rolled_back = self.undo_log_manager.abort_transaction(
                        transaction_id
                    )
                    resources_cleaned.append(
                        f"Rolled back {len(rolled_back)} operations for TX {transaction_id}"
                    )

                if hasattr(self.strategy, "abort_transaction"):
                    self.strategy.abort_transaction(transaction_id)
                    resources_cleaned.append(
                        f"Strategy abort cleanup for TX {transaction_id}"
                    )

                self.tx_manager.fail_transaction(
                    transaction_id,
                    (
                        "Validation failed"
                        if validation_errors
                        else "User requested abort"
                    ),
                )
                self.tx_manager.abort_transaction(transaction_id)
                resources_cleaned.append(f"Transaction {transaction_id} aborted")

            self.strategy.end_transaction(transaction_id)
            resources_cleaned.append(
                f"Strategy cleanup (locks released) for TX {transaction_id}"
            )

            self.tx_manager.terminate_transaction(transaction_id)
            resources_cleaned.append(f"Transaction {transaction_id} terminated")

        except Exception as e:
            result = EndTransactionResult.RESOURCE_CLEANUP_FAILED
            validation_errors.append(f"Error: {str(e)}")

            tx = self.tx_manager.get_transaction(transaction_id)
            current_status = tx.status if tx else None

            try:
                self.strategy.end_transaction(transaction_id)
            except Exception:
                pass

            if current_status and current_status != TransactionStatus.TERMINATED:
                try:
                    if current_status not in [
                        TransactionStatus.COMMITTED,
                        TransactionStatus.ABORTED,
                    ]:
                        self.tx_manager.fail_transaction(
                            transaction_id, "Emergency cleanup"
                        )
                        self.tx_manager.abort_transaction(transaction_id)

                    self.tx_manager.terminate_transaction(transaction_id)
                except Exception:
                    pass

            raise

        end_time = datetime.now()
        execution_time_ms = (end_time - start_time).total_seconds() * 1000

        report = EndTransactionReport(
            transaction_id=transaction_id,
            result=result,
            timestamp=end_time,
            locks_released=locks_released,
            resources_cleaned=resources_cleaned,
            validation_errors=validation_errors,
            execution_time_ms=execution_time_ms,
        )

        self.end_transaction_history.append(report)
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
            write_write_conflict = tx.write_set.intersection(other_tx.write_set)
            if write_write_conflict:
                errors.append(
                    f"Write-Write conflict dengan TX {other_tx_id} "
                    f"pada objek: {write_write_conflict}"
                )
                valid = False

        return {"valid": valid, "errors": errors}

    def _release_resources_list(
        self, transaction_id: int, accessed_objects: set
    ) -> List[str]:
        released = []

        for obj_id in accessed_objects:
            released.append(f"Resource: {obj_id}")

        return released

    def get_transaction_report(
        self, transaction_id: int
    ) -> Optional[EndTransactionReport]:
        for report in reversed(self.end_transaction_history):
            if report.transaction_id == transaction_id:
                return report
        return None

    def get_statistics(self) -> Dict[str, Any]:
        total = len(self.end_transaction_history)
        successful = sum(
            1
            for r in self.end_transaction_history
            if r.result == EndTransactionResult.SUCCESS
        )
        failed = sum(
            1
            for r in self.end_transaction_history
            if r.result == EndTransactionResult.FAILED
        )
        validation_failed = sum(
            1
            for r in self.end_transaction_history
            if r.result == EndTransactionResult.VALIDATION_FAILED
        )

        avg_time = (
            sum(r.execution_time_ms for r in self.end_transaction_history) / total
            if total > 0
            else 0
        )

        return {
            "total_ended": total,
            "successful": successful,
            "failed": failed,
            "validation_failed": validation_failed,
            "avg_execution_time_ms": avg_time,
            "success_rate": (successful / total * 100) if total > 0 else 0,
        }

    def print_statistics(self):
        stats = self.get_statistics()
        print("\n" + "=" * 60)
        print("END TRANSACTION STATISTICS")
        print("=" * 60)
        print(f"Total Transactions Ended: {stats['total_ended']}")
        print(f"Successful: {stats['successful']} ({stats['success_rate']:.1f}%)")
        print(f"Failed: {stats['failed']}")
        print(f"Validation Failed: {stats['validation_failed']}")
        print(f"Average Execution Time: {stats['avg_execution_time_ms']:.2f} ms")
        print("=" * 60 + "\n")
