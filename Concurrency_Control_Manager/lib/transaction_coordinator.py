from typing import Any
from .transaction_model import TransactionManager, TransactionStatus, Transaction
from .strategy_interface import ConcurrencyStrategy, Response


class TransactionCoordinator:

    def __init__(self, tx_manager: TransactionManager, strategy: ConcurrencyStrategy):
        self.tx_manager = tx_manager
        self.strategy = strategy

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
        try:
            tx = self.tx_manager.get_transaction(transaction_id)
            if tx and tx.status == TransactionStatus.ACTIVE:
                self.tx_manager.mark_partially_committed(transaction_id)

            self.tx_manager.commit_transaction(transaction_id)
            self.strategy.end_transaction(transaction_id)
            self.tx_manager.terminate_transaction(transaction_id)

        except Exception as e:
            self.abort(transaction_id, f"Commit failed: {e}")
            raise

    def abort(self, transaction_id: int, reason: str = "User requested"):
        tx = self.tx_manager.get_transaction(transaction_id)
        if not tx:
            return

        if tx.status == TransactionStatus.ACTIVE:
            self.tx_manager.fail_transaction(transaction_id, reason)

        self.tx_manager.abort_transaction(transaction_id)
        self.strategy.end_transaction(transaction_id)
        self.tx_manager.terminate_transaction(transaction_id)

    def _validate_active_transaction(self, transaction_id: int) -> Transaction:
        tx = self.tx_manager.get_transaction(transaction_id)
        if not tx:
            raise ValueError(f"Transaction {transaction_id} tidak ditemukan!")

        if tx.status != TransactionStatus.ACTIVE:
            raise ValueError(
                f"Transaction {transaction_id} tidak ACTIVE. Status: {tx.status.value}"
            )

        return tx
