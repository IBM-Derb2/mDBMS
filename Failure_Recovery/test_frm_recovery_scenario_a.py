import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

# Mock BufferManager (Updated untuk Callback Pattern & Recovery Support)
class MockBufferManager:
    def __init__(self):
        self.fetch_callback = None
        self.write_callback = None

    def set_load_table_routine(self, callback):
        self.fetch_callback = callback
    
    def set_save_buffer_routine(self, callback):
        self.write_callback = callback
        
    def is_buffer_almost_full(self):
        return False
    
    def flush_dirty_blocks(self):
        print("[MockBuffer] Flushing all dirty blocks...")
    
    # --- Penambahan Method Baru untuk Recovery ---
    def write_to_buffer_for_recovery(self, table, pk, data):
        # Simulasi sukses menulis ke buffer saat recovery
        print(f"   [MockBuffer] RECOVERY WRITE: {table} PK={pk} -> Buffer Updated")
    
    def delete_from_buffer_for_recovery(self, table, pk):
        # Simulasi sukses menghapus dari buffer saat recovery
        print(f"   [MockBuffer] RECOVERY DELETE: {table} PK={pk} -> Buffer Cleared")

# Enhanced Mock StorageEngine with operation tracking
class MockStorageEngine:
    def __init__(self):
        self.data = {}  # table -> {pk -> row_data}
        self.operations = []  # List of (op_type, table, pk, data)
    
    def write_block(self, data_write):
        """Mock write_block - simulate insert/update"""
        table = data_write.table
        conditions = data_write.conditions
        column = data_write.column
        new_value = data_write.new_value
        
        if table not in self.data:
            self.data[table] = {}
        
        # If no conditions, this is an INSERT (create new row)
        if not conditions:
            # Determine PK column based on table
            pk_columns = {
                'student': 'StudentID',
                'course': 'CourseID',
                'attends': 'StudentID'  # Composite key, use StudentID as primary
            }
            pk_col = pk_columns.get(table)
            
            new_pk = new_value if len(column) == 1 and column[0] == pk_col else None
            if new_pk:
                if new_pk not in self.data[table]:
                    self.data[table][new_pk] = {column[0]: new_value}
                    self.operations.append(('insert', table, new_pk, {column[0]: new_value}))
                    return type('Rows', (), {'rows_count': 1, 'data': [self.data[table][new_pk]]})()
        else:
            # UPDATE existing row
            pk_value = None
            for cond in conditions:
                if hasattr(cond, 'column') and hasattr(cond, 'value'):
                    pk_value = cond.value
                    break
            
            if pk_value and pk_value in self.data[table]:
                if isinstance(column, list) and len(column) > 0:
                    col_name = column[0]
                    self.data[table][pk_value][col_name] = new_value
                    self.operations.append(('update', table, pk_value, {col_name: new_value}))
                    return type('Rows', (), {'rows_count': 1, 'data': [self.data[table][pk_value]]})()
        
        return type('Rows', (), {'rows_count': 0, 'data': []})()
    
    def delete_block(self, data_deletion):
        """Mock delete_block - simulate delete"""
        table = data_deletion.table
        conditions = data_deletion.conditions
        
        if table not in self.data:
            return 0
        
        pk_value = None
        for cond in conditions:
            if hasattr(cond, 'column') and hasattr(cond, 'value'):
                pk_value = cond.value
                break
        
        if pk_value and pk_value in self.data[table]:
            deleted_row = self.data[table].pop(pk_value)
            self.operations.append(('delete', table, pk_value, deleted_row))
            return 1
        
        return 0
    
    def read_block(self, data_retrieval):
        """Mock read_block - simulate read"""
        return type('Rows', (), {'rows_count': 0, 'data': []})()

def main():
    print("="*70)
    print("Recovery Test - Scenario A")
    print("With Checkpoint, Mixed Outcomes (COMMIT/ABORT/CRASH)")
    print("="*70)
    print("\n📋 Database Schema:")
    print("  • student(StudentID, FullName, GPA)")
    print("  • course(CourseID, Year, CourseName, CourseDescription)")
    print("  • attends(StudentID, CourseID, Year)")
    
    log_dir = "test_recovery_logs_a"
    os.makedirs(log_dir, exist_ok=True)
    
    # Clean up old logs
    for f in os.listdir(log_dir):
        try:
            os.remove(os.path.join(log_dir, f))
        except:
            pass
    
    # Initialize FRM
    buffer_mgr = MockBufferManager()
    storage_engine = MockStorageEngine()
    
    # [UPDATED] Menggunakan Callback Pattern
    frm = FailureRecoveryManager(
        buffer_manager=buffer_mgr, 
        load_table_callback=storage_engine.read_block,  # Callback Baca
        save_buffer_callback=storage_engine.write_block, # Callback Tulis
        log_directory=log_dir
    )
    
    print("\n" + "="*70)
    print("PHASE 1: Normal Operations (Before Crash)")
    print("="*70)
    
    # TX 301: START → INSERT student → UPDATE student → (will COMMIT after checkpoint)
    print("\n[TX 301] Starting transaction...")
    frm.notify_transaction_start(301)
    frm.write_log_entry(301, WalAction.START)
    
    print("[TX 301] INSERT operation on student")
    frm.log_write(
        tx_id=301,
        table="student",
        pk={"StudentID": 99301},
        old_data=None,  # INSERT
        new_data={"StudentID": 99301, "FullName": "Alice Test", "GPA": 3.8}
    )
    
    # TX 302: START → INSERT course → UPDATE course → (will ABORT after checkpoint)
    print("\n[TX 302] Starting transaction...")
    frm.notify_transaction_start(302)
    frm.write_log_entry(302, WalAction.START)
    
    print("[TX 302] INSERT operation on course")
    frm.log_write(
        tx_id=302,
        table="course",
        pk={"CourseID": 99302},
        old_data=None,  # INSERT
        new_data={"CourseID": 99302, "Year": 2025, "CourseName": "Data Structures", "CourseDescription": "Learn about trees and graphs"}
    )
    
    # TX 303: START → INSERT attends → DELETE attends → (will CRASH - no COMMIT/ABORT)
    print("\n[TX 303] Starting transaction...")
    frm.notify_transaction_start(303)
    frm.write_log_entry(303, WalAction.START)
    
    print("[TX 303] INSERT operation on attends")
    frm.log_write(
        tx_id=303,
        table="attends",
        pk={"StudentID": 99303, "CourseID": 1},
        old_data=None,  # INSERT
        new_data={"StudentID": 99303, "CourseID": 1, "Year": 2025}
    )
    
    # CHECKPOINT [301, 302, 303]
    print("\n" + "="*70)
    print("CHECKPOINT: Saving state...")
    print("="*70)
    ongoing_txs = list(frm.active_transactions)
    frm.save_checkpoint(ongoing_txs)
    print(f"Checkpoint saved with ongoing transactions: {ongoing_txs}")

    # ⭐ AFTER CHECKPOINT - Add more operations
    print("\n[TX 301] Additional UPDATE after checkpoint (student)")
    frm.log_write(
        tx_id=301,
        table="student",
        pk={"StudentID": 99301},
        old_data={"StudentID": 99301, "FullName": "Alice Test", "GPA": 3.8},
        new_data={"StudentID": 99301, "FullName": "Alice Test", "GPA": 4.0}
    )

    print("[TX 302] Additional UPDATE after checkpoint (course)")
    frm.log_write(
        tx_id=302,
        table="course",
        pk={"CourseID": 99302},
        old_data={"CourseID": 99302, "Year": 2025, "CourseName": "Data Structures", "CourseDescription": "Learn about trees and graphs"},
        new_data={"CourseID": 99302, "Year": 2025, "CourseName": "Data Structures Advanced", "CourseDescription": "Advanced topics"}
    )

    print("[TX 303] Additional DELETE after checkpoint (attends)")
    frm.log_write(
        tx_id=303,
        table="attends",
        pk={"StudentID": 99303, "CourseID": 1},
        old_data={"StudentID": 99303, "CourseID": 1, "Year": 2025},
        new_data=None  # DELETE
    )

    # TX 301: COMMIT (after checkpoint)
    print("\n[TX 301] Committing...")
    frm.write_log_entry(301, WalAction.COMMIT)
    frm.notify_transaction_end(301)
    
    # TX 302: ABORT (after checkpoint)
    print("\n[TX 302] Aborting...")
    frm.write_log_entry(302, WalAction.ABORT)
    frm.abort_transaction(302)
    frm.notify_transaction_end(302)
    
    # TX 303: CRASH - no COMMIT/ABORT written!
    print("\n[TX 303] Still ongoing (no commit/abort yet)...")
    
    print("\n" + "="*70)
    print("💥 SYSTEM CRASH! 💥")
    print("="*70)
    print("System restarting...\n")
    
    # Simulate system restart - create new FRM instance
    print("="*70)
    print("PHASE 2: Recovery After Crash")
    print("="*70)
    
    # [UPDATED] Menggunakan Callback Pattern untuk instance recovery juga
    frm_recovery = FailureRecoveryManager(
        buffer_manager=buffer_mgr, 
        load_table_callback=storage_engine.read_block,
        save_buffer_callback=storage_engine.write_block,
        log_directory=log_dir
    )
    
    # Call recovery
    stats = frm_recovery.recover()
    
    # Verify results
    print("\n" + "="*70)
    print("PHASE 3: Verification")
    print("="*70)
    
    print("\n[EXPECTED BEHAVIOR]")
    print("-" * 70)
    print("✓ Checkpoint found with TX [301, 302, 303]")
    print("✓ REDO phase (operations after checkpoint):")
    print("  - TX 301 UPDATE student (GPA: 3.8 → 4.0) - committed ✓")
    print("  - TX 302 UPDATE course (name change) - will be aborted ✗")
    print("  - TX 303 DELETE attends - incomplete ⏳")
    print("✓ After REDO, undo_list contains: TX 303 only")
    print("  (TX 301 committed, TX 302 explicitly aborted)")
    print("✓ UNDO phase:")
    print("  - Undo TX 303 DELETE on attends (re-insert record)")
    print("  - Write CLR for TX 303")
    print("  - Write ABORT for TX 303")
    
    print("\n[ACTUAL RESULTS]")
    print("-" * 70)
    print(f"Checkpoint found: {stats['checkpoint_found']}")
    print(f"Checkpoint transactions: {stats['checkpoint_transactions']}")
    print(f"REDO operations: {stats['redo_count']}")
    print(f"UNDO operations: {stats['undo_count']}")
    
    # Assertions
    print("\n[VALIDATION]")
    print("-" * 70)
    
    try:
        assert stats['checkpoint_found'], "❌ Checkpoint should be found!"
        assert 301 in stats['checkpoint_transactions'], "❌ TX 301 should be in checkpoint!"
        assert 302 in stats['checkpoint_transactions'], "❌ TX 302 should be in checkpoint!"
        assert 303 in stats['checkpoint_transactions'], "❌ TX 303 should be in checkpoint!"
        
        # Expected REDO: 3 operations after checkpoint (1 from each TX)
        assert stats['redo_count'] == 3, f"❌ Should REDO 3 operations (after checkpoint), got {stats['redo_count']}"
        
        # Expected UNDO: 2 operation (TX 303 DELETE on attends)
        assert stats['undo_count'] == 2, f"❌ Should UNDO 2 operations (TX 303 has 2 ops), got {stats['undo_count']}"
        
        print("✅ All validations passed!")
    except AssertionError as e:
        print(f"{e}")
        print("\n⚠️  Some validations failed - check recovery logic")
    
    print("\n" + "="*70)
    print("TEST COMPLETED!")
    print("="*70)

if __name__ == "__main__":
    main()