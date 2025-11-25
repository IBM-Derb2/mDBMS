import threading
import time
import json
from datetime import datetime
from typing import Set, Optional
from log_config import WalType, WalAction, MockChangeReport
from log_writer import LogWriter
from log_parser import LogParser
from recovery_model import RecoverCriteria

class FailureRecoveryManager:
    """
    Manages Write-Ahead Logging (WAL), checkpointing, and recovery.
    
    Architecture:
    - FRM maintains its own active_transactions set
    - CC Manager notifies FRM via callbacks (notify_transaction_start/end)
    - Background thread monitors buffer and triggers checkpoint
    """
    
    def __init__(self, buffer_manager, storage_engine, 
                 log_directory: str = "wal_logs",
                 checkpoint_interval: int = 10):
        """
        Initialize Failure Recovery Manager.
        
        Args:
            buffer_manager: Reference to BufferManager
            storage_engine: Reference to StorageEngine  
            log_directory: Directory untuk WAL files
            checkpoint_interval: Checkpoint check interval (seconds)
        """
        # References to other managers
        self.buffer_manager = buffer_manager
        self.storage_engine = storage_engine
        
        # WAL components
        self.wal_writer = LogWriter(log_directory)
        self.wal_parser = LogParser(log_directory)
        
        # Track active transactions
        self.active_transactions: Set[int] = set()
        self.lock = threading.Lock()
        
        # Checkpoint routine
        self.checkpoint_interval = checkpoint_interval
        self.checkpoint_thread = None
        self.running = False
        
        print(f"[FRM] Initialized with log directory: {log_directory}")
    
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
            print(f"[FRM] TX {tx_id} started (active: {len(self.active_transactions)})")
    
    def notify_transaction_end(self, tx_id: int):
        """
        Called by CC Manager when transaction commits/aborts.
        Removes from active_transactions set.
        """
        with self.lock:
            self.active_transactions.discard(tx_id)
            print(f"[FRM] TX {tx_id} ended (active: {len(self.active_transactions)})")
    
    def write_log_entry(self, tx_id: int, action: WalAction):
        """
        Log START/COMMIT/ABORT entries to WAL.
        Called by CC Manager.
        
        Args:
            tx_id: Transaction ID
            action: START, COMMIT, or ABORT
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.EXECUTION.value,
            "action": action.value,
            "transaction_id": tx_id
            # No table/record info for lifecycle events
        }
        
        log_str = json.dumps(log_entry)
        self.wal_writer.write_to_file(log_str)
        
        print(f"[FRM] Logged {action.value.upper()} for TX {tx_id}")

    
    # ========== WRITE OPERATIONS (Called by BufferManager) ==========
    
    def log_write(self, tx_id: int, table: str, pk: dict, 
                  old_data: dict, new_data: dict):
        """
        Log INSERT/UPDATE/DELETE operations to WAL.
        Called by BufferManager during write_block.
        
        Determines action type:
        - old_data is None → INSERT
        - new_data is None → DELETE  
        - both not None → UPDATE
        
        Args:
            tx_id: Transaction ID
            table: Table name
            pk: Primary key dict
            old_data: Data before change (None for INSERT)
            new_data: Data after change (None for DELETE)
        """
        # Determine action type (INSERT/UPDATE/DELETE)
        action = self._determine_action(old_data, new_data)
        
        # Create WAL entry (Minimalist approach - no redundant fields)
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.EXECUTION.value,
            "action": action.value,
            "transaction_id": tx_id,
            "tablename": table,
            "pk_value": pk,
            "record_before": old_data,
            "record_after": new_data
        }
        
        # Convert to JSON string
        log_str = json.dumps(log_entry)
        
        # Write to WAL file
        self.wal_writer.write_to_file(log_str)
        
        print(f"[FRM] Logged {action.value.upper()} for TX {tx_id} on {table}")

    
    # ========== ABORT & ROLLBACK ==========
    
    def abort_transaction(self, tx_id: int):
        """
        Rollback all changes for aborted transaction.
        Called by CC Manager when transaction aborts.
        
        Uses Approach 1 (Blind Undo - Idempotent):
        - Always apply undo regardless of disk state
        - Safe to run multiple times (idempotent)
        - Prioritizes correctness over optimization
        
        Process:
        1. Read WAL backward for this transaction
        2. UNDO all WRITE operations (INSERT/UPDATE/DELETE)
        3. Apply changes via storage_engine
        
        Args:
            tx_id: Transaction ID to abort
        """
        print(f"\n[FRM] Starting rollback for TX {tx_id}...")
        
        # Collect all write operations for this transaction
        undo_operations = []
        
        # Read WAL backward until we find START for this transaction
        criteria = RecoverCriteria(transaction_id=tx_id)
        for entry in self.wal_parser.iter_backward(criteria):
            if entry.transaction_id != tx_id:
                continue
            
            # Stop when we reach START
            if entry.action == "start":
                print(f"[FRM] Found START for TX {tx_id}")
                break
            
            # Collect write operations (insert/update/delete)
            if entry.action in ["insert", "update", "delete"]:
                undo_operations.append(entry)
                print(f"[FRM] Found {entry.action.upper()} on {entry.table_name}")
        
        if not undo_operations:
            print(f"[FRM] No write operations to undo for TX {tx_id}")
            return
        
        print(f"[FRM] Found {len(undo_operations)} operations to undo")
        
        # Apply undo operations (already in reverse order from backward scan)
        for entry in undo_operations:
            self._apply_undo(entry, write_compensation_log=False)
        
        print(f"[FRM] Rollback completed for TX {tx_id}\n")
    
    def _apply_undo(self, entry, write_compensation_log=False):
        """
        Apply undo for a single write operation.
        
        Strategy (Idempotent - Blind Undo):
        - INSERT: DELETE the inserted record
        - UPDATE: Restore old values
        - DELETE: Re-insert the deleted record
        
        Args:
            entry: LogEntry with write operation details
            write_compensation_log: If True, write CLR to WAL
        """
        action = entry.action
        table = entry.table_name
        pk = entry.pk_value
        old_data = entry.old_data
        new_data = entry.new_data
        
        print(f"  [FRM] Undoing {action.upper()} on {table} (pk={pk})")
        
        if action == "insert":
            # Undo INSERT: DELETE the record
            # In real implementation, call: self.storage_engine.delete_block(...)
            print(f"    -> Would DELETE record from {table} WHERE pk={pk}")
            
        elif action == "update":
            # Undo UPDATE: Restore old_data
            # In real implementation, call: self.storage_engine.write_block(...)
            print(f"    -> Would UPDATE {table} SET {old_data} WHERE pk={pk}")
            
        elif action == "delete":
            # Undo DELETE: Re-insert old_data
            # In real implementation, call: self.storage_engine.write_block(...)
            print(f"    -> Would INSERT {old_data} into {table}")
        
        if write_compensation_log:
            self._write_compensation_log(entry)
        # Note: Actual storage_engine calls will be added when integrating
        # with real StorageEngine that has proper DataWrite/DataDeletion classes

    # ========== CHECKPOINT ==========
    
    def _checkpoint_routine(self):
        """
        Background thread that periodically checks buffer
        and triggers checkpoint when buffer almost full.
        """
        print(f"[FRM] Checkpoint routine running (interval: {self.checkpoint_interval}s)")
        
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
        checkpoint_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.CHECKPOINT.value,
            "ongoing_transactions": ongoing_transactions
        }
        
        checkpoint_str = json.dumps(checkpoint_entry)
        self.wal_writer.write_to_file(checkpoint_str)
        
        print(f"[FRM] Checkpoint entry written to WAL")
        print(f"[FRM] ===== CHECKPOINT COMPLETE =====\n")

    # ========== RECOVERY ==========
    
    def recover(self):
        """
        Recover database from WAL after crash.
        
        Algorithm (from slide):
        1. Find last checkpoint, initialize undo_list
        2. REDO phase: scan forward, update undo_list
        3. UNDO phase: scan backward, undo incomplete transactions
        
        Returns:
            dict: Recovery statistics for debugging
        """
        print("\n[FRM] ===== RECOVERY START =====")
        
        # Phase 1: Find checkpoint and initialize undo_list
        checkpoint_found, checkpoint_data, entries_after = self._find_last_checkpoint()
        
        if checkpoint_found:
            undo_list = set(checkpoint_data.get("ongoing_transactions", []))
            print(f"[FRM] Found checkpoint with {len(undo_list)} ongoing transactions: {undo_list}")
        else:
            undo_list = set()
            print("[FRM] No checkpoint found, starting recovery from beginning")
        
        # Phase 2: REDO phase (scan forward from checkpoint)
        print("\n[FRM] ===== REDO PHASE =====")
        
        # Reverse entries_after to get forward order
        entries_after.reverse()
        
        redo_count = 0
        for entry in entries_after:
            tx_id = entry.transaction_id
            action = entry.action
            
            # REDO write operations (INSERT/UPDATE/DELETE)
            if action in ["insert", "update", "delete"]:
                print(f"[FRM] REDO: TX {tx_id} {action.upper()} on {entry.table_name}")
                self._apply_redo(entry)
                redo_count += 1
            
            # Handle transaction lifecycle
            elif action == "start":
                print(f"[FRM] TX {tx_id} started")
                undo_list.add(tx_id)
            
            elif action == "commit":
                print(f"[FRM] TX {tx_id} committed")
                undo_list.discard(tx_id)  # Remove from undo_list
            
            elif action == "abort":
                print(f"[FRM] TX {tx_id} aborted")
                undo_list.discard(tx_id)  # Already rolled back
        
        print(f"[FRM] REDO complete: {redo_count} operations re-applied")
        print(f"[FRM] Transactions needing UNDO: {undo_list}")
        # Phase 3: UNDO phase (scan backward from end)
        print("\n[FRM] ===== UNDO PHASE =====")

        undo_count = 0

        # Scan backward through ALL logs (not just entries_after)
        for entry in self.wal_parser.iter_backward():
            
            # Stop condition: undo_list is empty
            if not undo_list:
                print("[FRM] All incomplete transactions undone, stopping scan")
                break
            
            tx_id = entry.transaction_id
            action = entry.action
            
            # Skip CLRs - already compensated, don't undo again
            if action == "clr":
                print(f"[FRM] Skipping CLR for TX {tx_id} (already compensated)")
                continue
            
            # Case 1: Write operations that need undo
            if tx_id in undo_list and action in ["insert", "update", "delete"]:
                print(f"[FRM] Undoing TX {tx_id} {action.upper()} on {entry.table_name}")
                self._apply_undo(entry, write_compensation_log=True)
                undo_count += 1
            
            # Case 2: Found START for incomplete transaction
            elif tx_id in undo_list and action == "start":
                print(f"[FRM] Found START for TX {tx_id}, writing ABORT")
                self.write_log_entry(tx_id, WalAction.ABORT)
                undo_list.remove(tx_id)
                print(f"[FRM] TX {tx_id} rollback complete, removed from undo_list")

        print(f"[FRM] UNDO complete: {undo_count} operations rolled back")

        # Phase 4: Return statistics
        # Phase 4: Return statistics
        print("[FRM] ===== RECOVERY COMPLETE =====\n")

        return {
            'checkpoint_found': checkpoint_found,
            'checkpoint_transactions': checkpoint_data.get('ongoing_transactions', []) if checkpoint_data else [],
            'redo_count': redo_count,
            'undo_list_final': list(undo_list),  # Should be empty!
            'undo_count': undo_count,
            'recovered': True
        }

    def _apply_redo(self, entry):
        """
        Re-apply a write operation to ensure it's on disk.
        
        Args:
            entry: LogEntry with write operation details
        """
        action = entry.action
        table = entry.table_name
        pk = entry.pk_value
        new_data = entry.new_data
        
        # REDO always uses new_data (after-image)
        if action == "insert":
            print(f"  [REDO] INSERT {new_data} into {table}")
            # self.storage_engine.write_block(...)
            
        elif action == "update":
            print(f"  [REDO] UPDATE {table} SET {new_data} WHERE pk={pk}")
            # self.storage_engine.write_block(...)
            
        elif action == "delete":
            print(f"  [REDO] DELETE from {table} WHERE pk={pk}")
            # self.storage_engine.delete_block(...)

    def _find_last_checkpoint(self):
        """Returns (found, checkpoint_data, entries_after_checkpoint)"""
        entries_after = []
        
        for entry in self.wal_parser.iter_backward():
            if entry.raw_log.get("type") == WalType.CHECKPOINT.value:
                return (True, entry.raw_log, entries_after)
            entries_after.append(entry)
        
        # No checkpoint - return all entries
        return (False, None, entries_after)
    
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
        self.wal_writer.write_to_file(clr_str)
        
        print(f"    [CLR] Compensation log written for TX {entry.transaction_id}")

    def _determine_action(self, old_data: dict, new_data: dict) -> WalAction:
        """
        Determine INSERT/UPDATE/DELETE based on old_data and new_data.
        
        Returns:
            WalAction: INSERT, UPDATE, or DELETE
        """
        if old_data is None:
            return WalAction.INSERT
        elif new_data is None:
            return WalAction.DELETE
        else:
            return WalAction.UPDATE
    
    def get_active_transaction_count(self) -> int:
        """Get number of active transactions (for monitoring)"""
        with self.lock:
            return len(self.active_transactions)
            