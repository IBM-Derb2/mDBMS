from typing import Any
import threading
from lib.strategy_interface import ConcurrencyStrategy, Response
from lib.lock_based_strategy import LockBasedStrategy
from lib.timestamp_based_strategy import TimestampBasedStrategy
from lib.validation_based_strategy import ValidationBasedStrategy
from lib.multi_version_strategy import MultiVersionStrategy
from lib.transaction_model import TransactionManager
from lib.transaction_coordinator import TransactionCoordinator
from lib.deadlock_detector import DeadlockDetector
from lib.transaction_id_generator import TransactionIdGenerator
from lib.undo_log import UndoLogManager


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
        self.undo_log_manager = UndoLogManager()
        self.strategy: ConcurrencyStrategy = LockBasedStrategy()
        self.id_generator = TransactionIdGenerator()
        self.coordinator = TransactionCoordinator(self.tx_manager, self.strategy)
        self.deadlock_detector = DeadlockDetector(self.tx_manager)

        # Set undo log manager in end transaction manager
        self.coordinator.end_tx_manager.undo_log_manager = self.undo_log_manager

        # Connect deadlock detector to coordinator
        self.coordinator.set_deadlock_detector(self.deadlock_detector)

        self._initialized = True
        print(
            f"[CCM] Manajer diinisialisasi (Singleton), strategi aktif: {self.strategy.__class__.__name__}"
        )
        print(
            f"[CCM] ACID Properties: [OK] Atomicity (Undo Log), [OK] Consistency, [OK] Isolation, [OK] Durability"
        )
        print(
            f"[CCM] Deadlock Prevention: {getattr(self.strategy, 'deadlock_prevention_scheme', 'N/A')}"
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
            print(f"[CCM] [OK] TX {transaction_id} berhasil di-commit dan terminated")
        except Exception as e:
            print(f"[CCM] [ERROR] Error saat commit TX {transaction_id}: {e}")
            raise

    def abort_transaction(self, transaction_id: int, reason: str = "User requested"):
        print(f"[CCM] Aborting TX {transaction_id} (Reason: {reason})...")
        try:
            self.coordinator.abort(transaction_id, reason)
            print(f"[CCM] [ABORTED] TX {transaction_id} berhasil di-abort dan terminated")
        except Exception as e:
            print(f"[CCM] Error saat abort TX {transaction_id}: {e}")
            raise

    def check_deadlock(self) -> bool:
        print("[CCM] Checking for deadlocks...")
        detected = self.deadlock_detector.check_and_resolve(self.abort_transaction)

        if detected:
            print(f"[CCM] [WARNING] DEADLOCK DETECTED and resolved")
        else:
            print("[CCM] [OK] No deadlock detected")

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
            self.coordinator.end_tx_manager.strategy = self.strategy

            # Reconnect tx_manager and deadlock callback to new strategy
            if hasattr(self.strategy, 'set_transaction_manager'):
                self.strategy.set_transaction_manager(self.tx_manager)
            if hasattr(self.strategy, 'set_deadlock_callback'):
                self.strategy.set_deadlock_callback(self.coordinator._on_potential_deadlock)

            print(f"[CCM] Mekanisme diubah ke: {self.strategy.__class__.__name__}")
            if hasattr(self.strategy, 'deadlock_prevention_scheme'):
                print(f"[CCM] Deadlock Prevention: {self.strategy.deadlock_prevention_scheme}")
        else:
            print(f"[CCM] Error: Algoritma '{mechanism}' tidak dikenal.")
