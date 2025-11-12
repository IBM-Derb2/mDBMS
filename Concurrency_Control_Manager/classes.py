from typing import Any
import threading
from .lib.strategy_interface import ConcurrencyStrategy, Response
from .lib.lock_based_strategy import LockBasedStrategy
from .lib.timestamp_based_strategy import TimestampBasedStrategy
from .lib.validation_based_strategy import ValidationBasedStrategy
from .lib.multi_version_strategy import MultiVersionStrategy
from .lib.transaction_model import TransactionManager
from .lib.transaction_coordinator import TransactionCoordinator
from .lib.deadlock_detector import DeadlockDetector
from .lib.transaction_id_generator import TransactionIdGenerator


class ConcurrencyControlManager:

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self.tx_manager = TransactionManager()
        self.strategy: ConcurrencyStrategy = LockBasedStrategy()
        self.id_generator = TransactionIdGenerator()
        self.coordinator = TransactionCoordinator(self.tx_manager, self.strategy)
        self.deadlock_detector = DeadlockDetector(self.tx_manager)

        self._initialized = True
        print(
            f"[CCM] Manajer diinisialisasi (Singleton), strategi aktif: {self.strategy.__class__.__name__}"
        )
        print(
            f"[CCM] ACID Properties: ✓ Atomicity, ✓ Consistency, ✓ Isolation, ✓ Durability"
        )

    def begin_transaction(self) -> int:
        print("[CCM] Beginning new transaction...")
        tid = self.id_generator.generate()
        self.tx_manager.create_transaction(tid)
        return tid

    def log_object(self, obj: Any, transaction_id: int, action: str):
        self.coordinator.execute_operation(obj, transaction_id, action)

    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        print(
            f"[CCM] Mendelegasikan VALIDATE '{action}' ke {self.strategy.__class__.__name__}"
        )
        return self.coordinator.validate_operation(obj, transaction_id, action)

    def end_transaction(self, transaction_id: int):
        print(
            f"[CCM] end_transaction() deprecated. Gunakan commit_transaction() atau abort_transaction()"
        )
        print(f"[CCM] Auto-committing TX {transaction_id}...")
        self.commit_transaction(transaction_id)

    def commit_transaction(self, transaction_id: int):
        print(f"[CCM] Committing TX {transaction_id}...")
        try:
            self.coordinator.commit(transaction_id)
            print(f"[CCM] ✓ TX {transaction_id} berhasil di-commit dan terminated")
        except Exception as e:
            print(f"[CCM] ✗ Error saat commit TX {transaction_id}: {e}")
            raise

    def abort_transaction(self, transaction_id: int, reason: str = "User requested"):
        print(f"[CCM] Aborting TX {transaction_id} (Reason: {reason})...")
        try:
            self.coordinator.abort(transaction_id, reason)
            print(f"[CCM] ⮌ TX {transaction_id} berhasil di-abort dan terminated")
        except Exception as e:
            print(f"[CCM] Error saat abort TX {transaction_id}: {e}")
            raise

    def check_deadlock(self) -> bool:
        print("[CCM] Checking for deadlocks...")
        detected = self.deadlock_detector.check_and_resolve(self.abort_transaction)

        if detected:
            print(f"[CCM] ⚠ DEADLOCK DETECTED and resolved")
        else:
            print("[CCM] ✓ No deadlock detected")

        return detected

    def get_transaction_status(self, transaction_id: int) -> str:
        tx = self.tx_manager.get_transaction(transaction_id)
        return tx.status.value if tx else "NOT_FOUND"

    def get_transaction_info(self, transaction_id: int) -> str:
        tx = self.tx_manager.get_transaction(transaction_id)
        return str(tx) if tx else f"Transaction {transaction_id} not found"

    def get_statistics(self) -> dict:
        stats = self.tx_manager.get_statistics()
        stats["strategy"] = self.strategy.__class__.__name__
        return stats

    def set_concurrency_mechanism(self, mechanism: str):
        strategies = {
            "lock-based": LockBasedStrategy,
            "timestamp-based": TimestampBasedStrategy,
            "validation-based": ValidationBasedStrategy,
            "multi-version": MultiVersionStrategy,
        }

        strategy_class = strategies.get(mechanism.lower())
        if strategy_class:
            self.strategy = strategy_class()
            self.coordinator.strategy = self.strategy
            print(f"[CCM] Mekanisme diubah ke: {self.strategy.__class__.__name__}")
        else:
            print(f"[CCM] Error: Algoritma '{mechanism}' tidak dikenal.")
