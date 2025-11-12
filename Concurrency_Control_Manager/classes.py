from typing import Any, Union
from .lib.strategy_interface import ConcurrencyStrategy, Action, Response
from .lib.lock_based_strategy import LockBasedStrategy
from .lib.timestamp_based_strategy import TimestampBasedStrategy
from .lib.validation_based_strategy import ValidationBasedStrategy
from .lib.multi_version_strategy import MultiVersionStrategy

class ConcurrencyControlManager:
    def __init__(self):
        self._next_tid = 1
        
        # default
        self.strategy: ConcurrencyStrategy = LockBasedStrategy()
        print(f"[CCM] Manajer diinisialisasi, strategi aktif: {self.strategy.__class__.__name__}")

    def begin_transaction(self) -> int:
        print("[CCM] Beginning new transaction.")
        tid = self._next_tid
        self._next_tid += 1
        return tid

    def log_object(self, obj: Any, transaction_id: int, action: str):
        self.strategy.log_object(obj, transaction_id, action)
        
    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        print(f"[CCM] Mendelegasikan VALIDATE '{action}' ke {self.strategy.__class__.__name__}")
        return self.strategy.validate_object(obj, transaction_id, action)

    def end_transaction(self, transaction_id: int):
        print(f"[CCM] Mendelegasikan END TX {transaction_id} ke {self.strategy.__class__.__name__}")
        self.strategy.end_transaction(transaction_id)


    # Metode ganti algoritma (BONUS)
    def set_concurrency_mechanism(self, mechanism: str):
        if mechanism.lower() == 'lock-based':
            self.strategy = LockBasedStrategy()
        elif mechanism.lower() == 'timestamp-based':
            self.strategy = TimestampBasedStrategy()
        elif mechanism.lower() == 'validation-based':
            self.strategy = ValidationBasedStrategy()
        elif mechanism.lower() == 'multi-version':
            self.strategy = MultiVersionStrategy()
        else:
            print(f"[CCM] Error: Algoritma '{mechanism}' tidak dikenal.")
            return 
            
        print(f"[CCM] Mekanisme diubah ke: {self.strategy.__class__.__name__}")