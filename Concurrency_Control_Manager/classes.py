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


class ConcurrencyControlManager:

    _instance = None
    _lock = threading.Lock()

    def __init__(self, frm):
        if hasattr(self, "_initialized"):
            return

        self.tx_manager = TransactionManager()
        self.frm = frm
        self.strategy: ConcurrencyStrategy = LockBasedStrategy()
        self.id_generator = TransactionIdGenerator()
        self.coordinator = TransactionCoordinator(self.tx_manager, self.strategy)
        self.deadlock_detector = DeadlockDetector(self.tx_manager)

        self.coordinator.set_deadlock_detector(self.deadlock_detector)
        self._initialized = True

    def begin_transaction(self, client_ip: str = None, client_port: int = None) -> str:
        tx_id = self.id_generator.generate(client_ip, client_port)
        self.tx_manager.create_transaction(tx_id)

        self.frm.get_log_history_manager().log_start(tx_id)
        self.frm.notify_transaction_start(tx_id)
        from Failure_Recovery.frm_types import WalAction
        self.frm.write_log_entry(tx_id, WalAction.START)

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

        self.frm.get_log_history_manager().log_commit(transaction_id)
        from Failure_Recovery.frm_types import WalAction
        self.frm.write_log_entry(transaction_id, WalAction.COMMIT)

        # Flush dirty blocks to disk on commit
        self.frm.buffer_manager.flush_dirty_blocks()

        self.frm.notify_transaction_end(transaction_id)

    def abort_transaction(self, transaction_id: int, reason: str = "User requested"):
        self.coordinator.abort(transaction_id, reason)

        self.frm.get_log_history_manager().log_abort(transaction_id)
        self.frm.abort_transaction(transaction_id)
        self.frm.notify_transaction_end(transaction_id)

    def log_operation(self, transaction_id: int, action: str, table_name: str):
        log_history = self.frm.get_log_history_manager()
        if action == "insert":
            log_history.log_insert(transaction_id, table_name)
        elif action == "update":
            log_history.log_update(transaction_id, table_name)
        elif action == "delete":
            log_history.log_delete(transaction_id, table_name)
        elif action == "select":
            log_history.log_select(transaction_id, table_name)

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
            self.strategy.set_deadlock_callback(
                self.coordinator._on_potential_deadlock)
        # NEW: Reconnect abort callback for wound-wait
        if hasattr(self.strategy, "set_abort_callback"):
            self.strategy.set_abort_callback(self.coordinator._auto_abort)
