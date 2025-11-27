from typing import Any
import threading
from Concurrency_Control_Manager.lib.strategy_interface import ConcurrencyStrategy, Response
from Concurrency_Control_Manager.lib.lock_based_strategy import LockBasedStrategy
from Concurrency_Control_Manager.lib.timestamp_based_strategy import TimestampBasedStrategy
from Concurrency_Control_Manager.lib.validation_based_strategy import ValidationBasedStrategy
from Concurrency_Control_Manager.lib.multi_version_strategy import MultiVersionStrategy
from Concurrency_Control_Manager.lib.transaction_model import TransactionManager
from Concurrency_Control_Manager.lib.transaction_coordinator import TransactionCoordinator
from Concurrency_Control_Manager.lib.deadlock_detector import DeadlockDetector
from Concurrency_Control_Manager.lib.transaction_id_generator import TransactionIdGenerator
from Concurrency_Control_Manager.lib.undo_log import UndoLogManager
from Concurrency_Control_Manager.lib.failure_recovery_adapter import FailureRecoveryAdapter
from Concurrency_Control_Manager.lib.mock_storage import MockStorageManager


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
        # Use FailureRecoveryAdapter instead of UndoLogManager for integration
        self.undo_log_manager = FailureRecoveryAdapter(log_directory="logs")
        self.mock_storage = MockStorageManager()  # NEW: Initialize mock storage
        self.undo_log_manager.set_storage_manager(
            self.mock_storage
        )  # NEW: Connect to undo log
        self.strategy: ConcurrencyStrategy = LockBasedStrategy()
        self.id_generator = TransactionIdGenerator()
        self.coordinator = TransactionCoordinator(self.tx_manager, self.strategy)
        self.deadlock_detector = DeadlockDetector(self.tx_manager)

        # Set undo log manager in end transaction manager
        self.coordinator.end_tx_manager.undo_log_manager = self.undo_log_manager

        # Connect deadlock detector to coordinator
        self.coordinator.set_deadlock_detector(self.deadlock_detector)
        self.frm = None
        self._initialized = True

    def set_failure_recovery_manager(self, frm):
        pass  # Reserved for future FRM integration

    def begin_transaction(self) -> int:
        tx_id = self.id_generator.generate()
        self.tx_manager.create_transaction(tx_id)
        self.undo_log_manager.log_start(tx_id)
        return tx_id

    def log_object(self, obj: Any, transaction_id: int, action: str):
        self.coordinator.execute_operation(obj, transaction_id, action)

    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        return self.coordinator.validate_operation(obj, transaction_id, action)

    def end_transaction(self, transaction_id: int):
        # Deprecated: use commit_transaction() or abort_transaction()
        self.commit_transaction(transaction_id)

    def commit_transaction(self, transaction_id: int):
        self.coordinator.commit(transaction_id)
        self.undo_log_manager.log_commit(transaction_id)

    def abort_transaction(self, transaction_id: int, reason: str = "User requested"):
        self.coordinator.abort(transaction_id, reason)

    def check_deadlock(self) -> bool:
        return self.deadlock_detector.check_and_resolve(self.abort_transaction)

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
        if not strategy_class:
            raise ValueError(f"Unknown concurrency mechanism: '{mechanism}'")

        self.strategy = strategy_class()
        self.coordinator.strategy = self.strategy
        self.coordinator.end_tx_manager.strategy = self.strategy

        # Reconnect tx_manager and deadlock callback to new strategy
        if hasattr(self.strategy, "set_transaction_manager"):
            self.strategy.set_transaction_manager(self.tx_manager)
        if hasattr(self.strategy, "set_deadlock_callback"):
            self.strategy.set_deadlock_callback(self.coordinator._on_potential_deadlock)
        # NEW: Reconnect abort callback for wound-wait
        if hasattr(self.strategy, "set_abort_callback"):
            self.strategy.set_abort_callback(self.coordinator._auto_abort)
