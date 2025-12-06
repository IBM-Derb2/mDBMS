import threading
import time

from typing import Any, Callable, Set
from .types import WalAction
from globalsy.loggers.wal_manager import WALManager
from globalsy.loggers.log_history import LogHistoryManager
from .recovery import RecoveryEngine


class FailureRecoveryManager:
    """
    Manages Write-Ahead Logging (WAL), checkpointing, and recovery.

    Architecture:
    - FRM maintains its own active_transactions set
    - CC Manager notifies FRM via callbacks (notify_transaction_start/end)
    - Background thread monitors buffer and triggers checkpoint
    """

    def __init__(self, buffer_manager,
                 load_table_callback: Callable[[str], Any],
                 save_buffer_callback: Callable[[Any], Any],
                 log_directory: str = "logs",
                 checkpoint_interval: int = 10):
        """
        Initialize Failure Recovery Manager.

        Args:
            buffer_manager: Reference to BufferManager
            load_table_callback: Function from SM to read disk (fetch)
            save_buffer_callback: Function from SM to save to disk (flush)
            log_directory: Directory for WAL files
            checkpoint_interval: Checkpoint check interval (seconds)
        """

        self.buffer_manager = buffer_manager

        self.wal_manager = WALManager(log_directory)
        self.log_history_manager = LogHistoryManager(log_directory)

        buffer_manager.set_load_table_routine(load_table_callback)
        buffer_manager.set_save_buffer_routine(save_buffer_callback)
        buffer_manager.set_wal_manager(self.wal_manager)

        self.recovery_engine = RecoveryEngine(
            log_directory, self.wal_manager, buffer_manager)

        # Track active transactions
        self.active_transactions: Set[int] = set()
        self.lock = threading.Lock()

        # Checkpoint routine
        self.checkpoint_interval = checkpoint_interval
        self.checkpoint_thread = None
        self.running = False

        print(f"[FRM] Initialized with log directory: {log_directory}")

    def get_wal_manager(self):
        return self.wal_manager

    def get_log_history_manager(self):
        return self.log_history_manager

    def get_buffered_row(self, table_name: str, pk_value: dict):
        """
        Get buffered row data if exists in buffer.

        Args:
            table_name: Table name
            pk_value: Primary key value dict

        Returns:
            Row data dict if buffered, None otherwise
        """
        key = self.buffer_manager._get_buffer_key(table_name, pk_value)
        if key in self.buffer_manager.buffer_data:
            return self.buffer_manager.buffer_data[key].data
        return None

    # ========== LIFECYCLE ==========

    def start(self):
        """Start checkpoint background thread"""
        self.running = True
        self.checkpoint_thread = threading.Thread(
            target=self._checkpoint_routine,
            daemon=True
        )
        self.checkpoint_thread.start()
        print("[FRM] Checkpoint routine started")

    def stop(self):
        """Stop checkpoint background thread"""
        self.running = False
        if self.checkpoint_thread:
            self.checkpoint_thread.join(timeout=5)
        print("[FRM] Checkpoint routine stopped")

    # ========== TRANSACTION LIFECYCLE (Called by CC Manager) ==========

    def notify_transaction_start(self, tx_id: int):
        """
        Called by CC Manager when transaction starts.
        Adds to active_transactions set.
        """
        with self.lock:
            self.active_transactions.add(tx_id)
            print(
                f"[FRM] TX {tx_id} started (active: {len(self.active_transactions)})")

    def notify_transaction_end(self, tx_id: int):
        """
        Called by CC Manager when transaction commits/aborts.
        Removes from active_transactions set.
        """
        with self.lock:
            self.active_transactions.discard(tx_id)
            print(
                f"[FRM] TX {tx_id} ended (active: {len(self.active_transactions)})")

    def write_log_entry(self, tx_id: int, action: WalAction):
        self.wal_manager.log_lifecycle(tx_id, action)
        print(f"[FRM] Logged {action.value.upper()} for TX {tx_id}")

    def log_write(self, tx_id: int, table: str, pk: dict,
                  old_data: dict, new_data: dict):
        self.wal_manager.log_operation(tx_id, table, pk, old_data, new_data)

        action = "UPDATE"
        if old_data is None:
            action = "INSERT"
        elif new_data is None:
            action = "DELETE"
        print(f"[FRM] Logged {action} for TX {tx_id} on {table}")

    # ========== ABORT & ROLLBACK ==========

    def abort_transaction(self, tx_id: int):
        self.write_log_entry(tx_id, WalAction.ABORT)
        self.recovery_engine.abort_transaction(tx_id)

    # ========== CHECKPOINT ==========

    def _checkpoint_routine(self):
        """
        Background thread that periodically checks buffer
        and triggers checkpoint when buffer almost full.
        """
        print(
            f"[FRM] Checkpoint routine running (interval: {self.checkpoint_interval}s)")

        while self.running:
            time.sleep(self.checkpoint_interval)

            # Check if buffer almost full
            if self.buffer_manager.is_buffer_almost_full():
                print("[FRM] Buffer almost full, triggering checkpoint...")
                with self.lock:
                    ongoing = list(self.active_transactions)
                self.save_checkpoint(ongoing)

    def save_checkpoint(self, ongoing_transactions: list):
        """
        Save checkpoint to WAL:
        1. Flush all dirty blocks to disk
        2. Write checkpoint entry with ongoing transactions
        3. Clear WAL entries before oldest ongoing transaction

        Args:
            ongoing_transactions: List of active transaction IDs
        """
        print(f"\n[FRM] ===== CHECKPOINT START =====")
        print(f"[FRM] Ongoing transactions: {ongoing_transactions}")

        # Step 1: Flush all dirty blocks to disk
        print(f"[FRM] Flushing all dirty blocks to disk...")
        self.buffer_manager.flush_dirty_blocks()
        print(f"[FRM] Flush completed - all dirty blocks now persisted")

        # Step 2: Write checkpoint entry to WAL
        self.wal_manager.log_checkpoint(ongoing_transactions)
        print(f"[FRM] Checkpoint entry written to WAL")

        # Step 3: Clear WAL entries before oldest ongoing transaction
        print(f"[FRM] Clearing WAL before oldest ongoing transaction...")
        self.clear_wal_after_checkpoint(ongoing_transactions)

        print(f"[FRM] ===== CHECKPOINT COMPLETE =====\n")

    def clear_wal_after_checkpoint(self, ongoing_transactions: list):
        """
        Clear WAL after checkpoint since data is now safely on disk.
        Keep only WAL entries from the oldest ongoing transaction onwards.

        Args:
            ongoing_transactions: List of active transaction IDs
        """
        print("[FRM] Starting WAL cleanup after checkpoint...")

        if not ongoing_transactions:
            print("[FRM] No ongoing transactions, clearing entire WAL")
            self.wal_manager.clear_entire_wal()
        else:
            print(f"[FRM] Clearing WAL before oldest ongoing transaction")
            self.wal_manager.clear_wal_before_oldest_transaction(
                ongoing_transactions)

        print("[FRM] WAL cleanup completed")

    # ========== RECOVERY ==========

    def recover(self):
        print("[FRM] Delegating recovery to RecoveryEngine...")
        return self.recovery_engine.recover()

    def _determine_action(self, old_data: dict, new_data: dict) -> WalAction:
        if old_data is None:
            return WalAction.INSERT
        elif new_data is None:
            return WalAction.DELETE
        else:
            return WalAction.UPDATE

    def get_active_transaction_count(self) -> int:
        with self.lock:
            return len(self.active_transactions)
