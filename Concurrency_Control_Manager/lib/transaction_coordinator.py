from typing import Any, Optional
from .transaction_model import TransactionManager, TransactionStatus, Transaction
from .strategy_interface import ConcurrencyStrategy, Response
from .end_transaction import EndTransactionManager, EndTransactionResult

class TransactionCoordinator:

    def __init__(self, tx_manager: TransactionManager, strategy: ConcurrencyStrategy):
        self.tx_manager = tx_manager
        self.strategy = strategy
        self.end_tx_manager = EndTransactionManager(tx_manager, strategy)
        self.deadlock_detector = None  # Will be set by ConcurrencyControlManager

        # Set tx_manager reference in strategy if it supports it
        if hasattr(strategy, 'set_transaction_manager'):
            strategy.set_transaction_manager(tx_manager)

        # Set deadlock callback if strategy supports it
        if hasattr(strategy, 'set_deadlock_callback'):
            strategy.set_deadlock_callback(self._on_potential_deadlock)

    def set_deadlock_detector(self, detector):
        """Set the deadlock detector instance."""
        self.deadlock_detector = detector

    def _on_potential_deadlock(self):
        """Callback triggered when a transaction enters wait state."""
        if self.deadlock_detector:
            # Check and resolve deadlock automatically
            detected = self.deadlock_detector.check_and_resolve(
                lambda tx_id, reason: self._auto_abort(tx_id, reason)
            )
            if detected:
                print("[Coordinator] [WARN]️ Deadlock was detected and resolved automatically")

    def _auto_abort(self, transaction_id: int, reason: str):
        """Internal abort method for deadlock resolution."""
        print(f"[Coordinator] Auto-aborting TX {transaction_id}: {reason}")
        try:
            self.abort(transaction_id, reason)
        except Exception as e:
            print(f"[Coordinator] Warning: Error during auto-abort of TX {transaction_id}: {e}")

    def execute_operation(self, obj: Any, transaction_id: int, action: str):
        tx = self._validate_active_transaction(transaction_id)
        tx.add_operation(action, str(obj))
        self.strategy.log_object(obj, transaction_id, action)

    def validate_operation(
        self, obj: Any, transaction_id: int, action: str
    ) -> Response:
        tx = self.tx_manager.get_transaction(transaction_id)
        if not tx:
            raise ValueError(f"Transaction {transaction_id} tidak ditemukan!")

        if tx.status != TransactionStatus.ACTIVE:
            return Response(allowed=False, transaction_id=transaction_id)

        return self.strategy.validate_object(obj, transaction_id, action)

    def commit(self, transaction_id: int):
        report = self.end_tx_manager.end_transaction(transaction_id, is_commit=True)
        if report.result != EndTransactionResult.SUCCESS:
            raise Exception(f"Commit failed: {report.validation_errors}")

    def abort(self, transaction_id: int, reason: str = "User requested"):
        report = self.end_tx_manager.end_transaction(transaction_id, is_commit=False)
        if report.result != EndTransactionResult.SUCCESS:
            print(f"[Warning] Abort TX {transaction_id} selesai dengan warning: {report.validation_errors}")

    def _validate_active_transaction(self, transaction_id: int) -> Transaction:
        tx = self.tx_manager.get_transaction(transaction_id)
        if not tx:
            raise ValueError(f"Transaction {transaction_id} tidak ditemukan!")

        if tx.status != TransactionStatus.ACTIVE:
            raise ValueError(
                f"Transaction {transaction_id} tidak ACTIVE. Status: {tx.status.value}"
            )

        return tx
