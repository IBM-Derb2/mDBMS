from datetime import datetime
import json
from typing import Dict, Any
from .frm_types import WalAction, WalType, RecoverCriteria
from .buffer_manager import BufferManager
from globalsy.loggers.wal_manager import WALManager


class RecoveryEngine:
    """Handles REDO/UNDO recovery and transaction rollback"""
    def __init__(self, log_directory: str = "test_logs", wal_manager=None, buffer_manager: BufferManager = None):
        self.wal_manager = wal_manager or WALManager(log_directory=log_directory)
        self.buffer_manager = buffer_manager

    def recover(self) -> Dict[str, Any]:
        """Execute full recovery: REDO committed, UNDO uncommitted"""
        print("\n[Recovery] ===== RECOVERY START =====")

        checkpoint_found, checkpoint_data, entries_after = self._find_last_checkpoint()

        if checkpoint_found:
            undo_list = set(checkpoint_data.get("ongoing_transactions", []))
            print(f"[Recovery] Found checkpoint with {len(undo_list)} ongoing transactions: {undo_list}")
        else:
            undo_list = set()
            print("[Recovery] No checkpoint found, starting recovery from beginning")

        print("\n[Recovery] ===== REDO PHASE =====")
        entries_after.reverse()
        redo_count = 0

        for entry in entries_after:
            tx_id = entry.transaction_id
            action = entry.action

            if action in ["insert", "update", "delete"]:
                print(f"[Recovery] REDO: TX {tx_id} {action.upper()} on {entry.table_name}")
                self._apply_redo(entry)
                redo_count += 1
            elif action == "start":
                undo_list.add(tx_id)
            elif action == "commit":
                undo_list.discard(tx_id)
            elif action == "abort":
                undo_list.discard(tx_id)

        print(f"[Recovery] REDO complete: {redo_count} operations re-applied")
        print(f"[Recovery] Transactions needing UNDO: {undo_list}")

        print("\n[Recovery] ===== UNDO PHASE =====")
        undo_count = 0

        for entry in self.wal_manager.iter_backward():
            if not undo_list:
                break

            tx_id = entry.transaction_id
            action = entry.action

            if action == "compensation":
                continue

            if tx_id in undo_list and action in ["insert", "update", "delete"]:
                print(f"[Recovery] Undoing TX {tx_id} {action.upper()} on {entry.table_name}")
                self._apply_undo(entry)
                self._write_compensation_log(entry)
                undo_count += 1
            elif tx_id in undo_list and action == "start":
                self._log_abort_for_incomplete_transaction(tx_id)
                undo_list.remove(tx_id)

        print(f"[Recovery] UNDO complete: {undo_count} operations rolled back")

        print("\n[Recovery] ===== FLUSHING RECOVERED DATA =====")
        if self.buffer_manager:
            self.buffer_manager.flush_dirty_blocks()
            print("[Recovery] All recovered data flushed to disk")

        print("[Recovery] ===== RECOVERY COMPLETE =====\n")

        return {
            'checkpoint_found': checkpoint_found,
            'checkpoint_transactions': checkpoint_data.get('ongoing_transactions', []) if checkpoint_data else [],
            'redo_count': redo_count,
            'undo_count': undo_count,
            'recovered': True
        }

    def abort_transaction(self, tx_id: int) -> None:
        """Rollback all operations of a transaction"""
        print(f"\n[Recovery] Starting rollback for TX {tx_id}...")

        undo_operations = []
        criteria = RecoverCriteria(transaction_id=tx_id)
        print(f"[Recovery Debug] Searching WAL backward for TX {tx_id}...")

        entry_count = 0
        for entry in self.wal_manager.iter_backward(criteria):
            entry_count += 1

            if entry.transaction_id != tx_id:
                continue

            if entry.action == "start":
                print(f"[Recovery Debug] Reached START for TX {tx_id}, stopping")
                break

            elif entry.action in ["insert", "update", "delete"]:
                print(f"[Recovery Debug] Found operation to undo: {entry.action}")
                undo_operations.append(entry)

        print(f"[Recovery Debug] Collected {len(undo_operations)} operations to undo")

        for entry in undo_operations:
            print(f"[Recovery] Undoing TX {tx_id} {entry.action.upper()} on {entry.table_name}")
            self._apply_undo(entry)
            self._write_compensation_log(entry)

        if self.buffer_manager:
            self.buffer_manager.flush_dirty_blocks()

        print(f"[Recovery] Rollback completed for TX {tx_id}\n")

    def _log_abort_for_incomplete_transaction(self, tx_id: int) -> None:
        """Write ABORT entry for incomplete transactions during recovery"""
        abort_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.EXECUTION.value,
            "action": WalAction.ABORT.value,
            "transaction_id": tx_id
        }
        abort_str = json.dumps(abort_entry)
        self.wal_manager.write_to_file(abort_str)
        print(f"[Recovery] Writing ABORT for incomplete TX {tx_id}")

    def _write_compensation_log(self, entry):
        """Write CLR (Compensation Log Record) to mark undo completion"""
        compensation_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.EXECUTION.value,
            "action": "compensation",
            "original_action": entry.action,
            "transaction_id": entry.transaction_id,
            "tablename": entry.table_name,
            "pk_value": entry.pk_value,
            "record_before": entry.new_data,
            "record_after": entry.old_data
        }

        compensation_str = json.dumps(compensation_entry)
        self.wal_manager.write_to_file(compensation_str)
        print(f"    [CLR] Compensation log written for TX {entry.transaction_id}")

    def _apply_redo(self, entry) -> None:
        """Re-apply operation using new_data (after-image)"""
        if not self.buffer_manager or not entry.table_name:
            print(f"    [Warning] Buffer manager not available, skipping REDO")
            return

        action = entry.action
        table = entry.table_name
        pk = entry.pk_value
        new_data = entry.new_data

        try:
            if action == "insert" and new_data:
                self.buffer_manager.write_to_buffer_for_recovery(table, pk, new_data)
            elif action == "update" and new_data and pk:
                self.buffer_manager.write_to_buffer_for_recovery(table, pk, new_data)
            elif action == "delete" and pk:
                self.buffer_manager.delete_from_buffer_for_recovery(table, pk)
        except Exception as e:
            print(f"    [Error] REDO failed: {e}")

    def _apply_undo(self, entry) -> None:
        """Undo operation: INSERT→delete, UPDATE→restore old, DELETE→reinsert"""
        action = entry.action
        table = entry.table_name
        pk = entry.pk_value
        old_data = entry.old_data

        print(f"  [Recovery] Undoing {action.upper()} on {table} (pk={pk})")

        if not self.buffer_manager:
            print(f"    [Warning] Buffer manager not available, skipping undo")
            return

        try:
            if action == "insert":
                self.buffer_manager.delete_from_buffer_for_recovery(table, pk)
            elif action == "update" and old_data and pk:
                self.buffer_manager.write_to_buffer_for_recovery(table, pk, old_data)
            elif action == "delete" and old_data:
                self.buffer_manager.write_to_buffer_for_recovery(table, pk, old_data)
        except Exception as e:
            print(f"    [Error] Undo failed: {e}")
            import traceback
            traceback.print_exc()

    def _find_last_checkpoint(self):
        """Find most recent checkpoint, return (found, data, entries_after)"""
        entries_after = []

        for entry in self.wal_manager.iter_backward():
            if entry.raw_log.get("type") == "checkpoint":
                return (True, entry.raw_log, entries_after)
            entries_after.append(entry)

        return (False, None, entries_after)