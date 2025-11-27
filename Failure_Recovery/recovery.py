from datetime import datetime
import json
from typing import Optional, Set, Dict, Any, List
from log_config import WalAction, WalType
from log_writer import LogWriter
from recovery_model import RecoverCriteria, LogEntry
from log_parser import LogParser
from buffer_manager import BufferManager
from Storage_Manager.utils import DataWrite, DataDeletion, Condition
from Storage_Manager.storage_engine import StorageEngine

class RecoveryEngine:
    def __init__(self, log_directory: str = "test_logs", buffer_manager: BufferManager = None, storage_engine: StorageEngine = None):
        self.log_parser = LogParser(log_directory=log_directory)
        self.log_writer = LogWriter(log_directory=log_directory)
        self.buffer_manager = buffer_manager
        self.storage_engine = storage_engine

    def recover(self) -> Dict[str, Any]:
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
        
        for entry in self.log_parser.iter_backward():
            if not undo_list:
                break
                
            tx_id = entry.transaction_id
            action = entry.action
            
            if action == "clr":
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
        print("[Recovery] ===== RECOVERY COMPLETE =====\n")
        
        return {
            'checkpoint_found': checkpoint_found,
            'checkpoint_transactions': checkpoint_data.get('ongoing_transactions', []) if checkpoint_data else [],
            'redo_count': redo_count,
            'undo_count': undo_count,
            'recovered': True
        }

    def abort_transaction(self, tx_id: int) -> None:
        print(f"\n[Recovery] Starting rollback for TX {tx_id}...")

        undo_operations = []
        criteria = RecoverCriteria(transaction_id=tx_id)
        for entry in self.log_parser.iter_backward(criteria):
            if entry.transaction_id != tx_id:
                continue
                
            if entry.action == "start":
                break

            elif entry.action in ["insert", "update", "delete"]:
                undo_operations.append(entry)
        
        for entry in undo_operations:
            print(f"[Recovery] Undoing TX {tx_id} {entry.action.upper()} on {entry.table_name}")
            self._apply_undo(entry)
            self._write_compensation_log(entry)
        
        print(f"[Recovery] Rollback completed for TX {tx_id}\n")

    def _log_abort_for_incomplete_transaction(self, tx_id: int) -> None:
        """NEW: Log ABORT for incomplete transactions found during recovery"""
        abort_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.EXECUTION.value,
            "action": WalAction.ABORT.value,
            "transaction_id": tx_id
        }
        abort_str = json.dumps(abort_entry)
        self.log_writer.write_to_file(abort_str)
        print(f"[Recovery] Writing ABORT for incomplete TX {tx_id}")
    
    def _write_compensation_log(self, entry):
        """
        Write Compensation Log Record (CLR) for undo operation.
        
        CLR Format (simplified):
        - action: 'clr' (special marker)
        - original_action: The action being undone (insert/update/delete)
        - transaction_id: Same as original
        - table_name: Same as original
        - pk_value: Same as original
        - record_before: null (CLR doesn't need before-image)
        - record_after: The value being restored (old_data from original)
        
        Purpose:
        - Marks that undo has been performed
        - Prevents re-doing the same undo on recovery restart
        - Makes recovery idempotent
        
        Args:
            entry: LogEntry being undone
        """
        clr_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.EXECUTION.value,
            "action": "clr",  # Special marker for compensation log
            "original_action": entry.action,  # What was undone
            "transaction_id": entry.transaction_id,
            "tablename": entry.table_name,
            "pk_value": entry.pk_value,
            "record_before": None,  # CLR has no before-image
            "record_after": entry.old_data  # The value we restored
        }
        
        clr_str = json.dumps(clr_entry)
        self.log_writer.write_to_file(clr_str)
        
        print(f"    [CLR] Compensation log written for TX {entry.transaction_id}")
        
    def _apply_redo(self, entry: LogEntry) -> None:
        """
        Re-apply a write operation to ensure it's on disk.
        
        Args:
            entry: LogEntry with write operation details
        """
        if not self.storage_engine or not entry.table_name:
            return
            
        action = entry.action
        table = entry.table_name
        pk = entry.pk_value
        new_data = entry.new_data

        # REDO always uses new_data (after-image)
        if action == "insert" and new_data:
            conditions = [Condition(k, "=", v) for k, v in pk.items()] if pk else []
            columns = list(new_data.keys())
            values = list(new_data.values())
            data_write = DataWrite(table, columns, conditions, values)
            self.storage_engine.write_block(data_write)
        elif action == "update" and new_data and pk:
            conditions = [Condition(k, "=", v) for k, v in pk.items()]
            columns = list(new_data.keys())
            values = list(new_data.values())
            data_write = DataWrite(table, columns, conditions, values)
            self.storage_engine.write_block(data_write)
        elif action == "delete" and pk:
            conditions = [Condition(k, "=", v) for k, v in pk.items()]
            data_deletion = DataDeletion(table, conditions)
            self.storage_engine.delete_block(data_deletion)

    def _apply_undo(self, entry: LogEntry) -> None:
        """
        Apply undo for a single write operation using idempotent blind undo strategy.
        
        Undo operations:
        - INSERT: Delete the inserted record
        - UPDATE: Restore old values
        - DELETE: Re-insert the deleted record
        
        Args:
            entry: LogEntry containing operation details to undo
        """
        action = entry.action
        table = entry.table_name
        pk = entry.pk_value
        old_data = entry.old_data

        print(f"  [Recovery] Undoing {action.upper()} on {table} (pk={pk})")

        has_storage = (
            self.storage_engine is not None and 
            hasattr(self.storage_engine, 'write_block') and 
            hasattr(self.storage_engine, 'delete_block')
        )

        if not has_storage:
            print(f"    [Warning] Storage engine not available, skipping undo")
            return

        try:
            if action == "insert":
                self._undo_insert(table, pk)
            elif action == "update" and old_data and pk:
                self._undo_update(table, pk, old_data)
            elif action == "delete" and old_data:
                self._undo_delete(table, pk, old_data)
        except Exception as e:
            print(f"    [Error] Undo failed: {e}")
            import traceback
            traceback.print_exc()

    def _undo_insert(self, table: str, pk: dict) -> None:
        """Undo INSERT by deleting the record"""
        from Storage_Manager.utils import DataDeletion, Condition
        
        print(f"    -> DELETE FROM {table} WHERE pk={pk}")
        conditions = [Condition(k, "=", v) for k, v in pk.items()]
        data_deletion = DataDeletion(table, conditions)
        deleted_count = self.storage_engine.delete_block(data_deletion)
        print(f"    [OK] Deleted {deleted_count} record(s)")

    def _undo_update(self, table: str, pk: dict, old_data: dict) -> None:
        """Undo UPDATE by restoring old values"""
        from Storage_Manager.utils import DataWrite, Condition
        
        print(f"    -> UPDATE {table} SET {old_data} WHERE pk={pk}")
        conditions = [Condition(k, "=", v) for k, v in pk.items()]
        pk_columns = set(pk.keys())
        
        for col_name, col_value in old_data.items():
            if col_name not in pk_columns:
                data_write = DataWrite(
                    table=table,
                    column=[col_name],
                    conditions=conditions,
                    new_value=col_value
                )
                self.storage_engine.write_block(data_write)
                print(f"    [OK] Restored {col_name} = {col_value}")

    def _undo_delete(self, table: str, pk: dict, old_data: dict) -> None:
        """Undo DELETE by re-inserting the record"""
        from Storage_Manager.utils import DataWrite, DataRetrieval, Condition
        
        print(f"    -> INSERT {old_data} INTO {table}")
        pk_columns = set(pk.keys()) if pk else set()
        
        for pk_col in pk_columns:
            if pk_col not in old_data:
                continue
                
            pk_value = old_data[pk_col]
            
            check_retrieval = DataRetrieval(
                table=table,
                column=["*"],
                conditions=[Condition(pk_col, "=", pk_value)],
                search_type="sequential"
            )
            existing = self.storage_engine.read_block(check_retrieval)
            
            if existing.rows_count > 0:
                print(f"    [Warning] Row with {pk_col}={pk_value} already exists")
                break
            
            data_write = DataWrite(
                table=table,
                column=[pk_col],
                conditions=[],
                new_value=pk_value
            )
            result = self.storage_engine.write_block(data_write)
            print(f"    [OK] Inserted PK {pk_col} (affected: {result.rows_count} rows)")
        
        conditions = [Condition(k, "=", v) for k, v in pk.items()] if pk else []
        for col_name, col_value in old_data.items():
            if col_name not in pk_columns:
                data_write = DataWrite(
                    table=table,
                    column=[col_name],
                    conditions=conditions,
                    new_value=col_value
                )
                result = self.storage_engine.write_block(data_write)
                
                if result.rows_count > 0:
                    print(f"    [OK] Set {col_name} = {col_value}")
                else:
                    print(f"    [Warning] Failed to set {col_name}")
        
        print(f"    [OK] Re-inserted record into {table}")
    
    def _find_last_checkpoint(self):
        """Returns (found, checkpoint_data, entries_after_checkpoint)"""
        entries_after = []
        
        for entry in self.log_parser.iter_backward():
            if entry.raw_log.get("type") == "checkpoint":
                return (True, entry.raw_log, entries_after)
            entries_after.append(entry)
        

        # No checkpoint - return all entries
        return (False, None, entries_after)