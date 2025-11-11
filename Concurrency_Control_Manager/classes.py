from dataclasses import dataclass
from typing import Any, Union
from .lib.strategy_interface import ConcurrencyStrategy
from .lib.lock_based_strategy import LockBasedStrategy


class ConcurrencyControlManager:
    def __init__(self):
        self._next_tid = 1
        
        #default
        self.strategy: ConcurrencyStrategy = LockBasedStrategy()

    def begin_transaction(self) -> int:
        print("[CCM Mock] Beginning new transaction.")
        tid = self._next_tid
        self._next_tid += 1
        return tid

    def log_object(self, obj: Any, transaction_id: int, action: str):
        self.strategy.log_object(obj, transaction_id, action)
        
    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        print(f"[CCM Mock] Validating action '{action}' on '{obj}' for TID: {transaction_id}")
        return Response(allowed=True, transaction_id=transaction_id)

    def end_transaction(self, transaction_id: int):
        print(f"[CCM Mock] Committing/Aborting and flushing objects for TID: {transaction_id}")


    # Metode ganti algoritma 
    def set_concurrency_mechanism(self, mechanism: str):
        if mechanism.lower() == 'lock-based':
            self.strategy = LockBasedStrategy()
            print("[CCM] Mekanisme diubah ke: Lock-Based")
        # elif mechanism.lower() == 'timestamp-based':
        #     self.strategy = TimestampBasedStrategy()
        #     print("[CCM] Algoritma diubah ke: Timestamp-Based")
        else:
            print(f"[CCM] Error: Algoritma '{mechanism}' tidak dikenal.")