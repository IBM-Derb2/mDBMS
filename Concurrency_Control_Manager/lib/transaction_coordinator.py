from typing import Any
from .transaction_model import TransactionManager, TransactionStatus, Transaction
from .strategy_interface import ConcurrencyStrategy, Response
from end_transaction import EndTransactionManager, EndTransactionResult

class TransactionCoordinator:

    def __init__(self, tx_manager: TransactionManager, strategy: ConcurrencyStrategy):
        self.tx_manager = tx_manager
        self.strategy = strategy
        self.end_tx_manager = EndTransactionManager(tx_manager, strategy)

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
