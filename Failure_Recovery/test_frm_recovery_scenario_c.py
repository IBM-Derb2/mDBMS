import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

# Mock BufferManager (Updated untuk Callback & Recovery)
class MockBufferManager:
    def __init__(self):
        self.fetch_callback = None
        self.write_callback = None

    def set_fetch_block_routine(self, callback):
        self.fetch_callback = callback
    
    def set_write_block_routine(self, callback):
        self.write_callback = callback

    def is_buffer_almost_full(self):
        return False
    
    def flush_dirty_blocks(self):
        print("[MockBuffer] Flushing all dirty blocks...")

    # Method tambahan untuk Recovery
    def write_to_buffer_for_recovery(self, table, pk, data):
        print(f"   [MockBuffer] RECOVERY WRITE: {table} PK={pk} -> Buffer Updated")
    
    def delete_from_buffer_for_recovery(self, table, pk):
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
        
        if not conditions: # INSERT
            pk_columns = {'student': 'StudentID', 'course': 'CourseID', 'attends': 'StudentID'}
            pk_col = pk_columns.get(table)
            new_pk = new_value if len(column) == 1 and column[0] == pk_col else None
            if new_pk:
                if new_pk not in self.data[table]:
                    self.data[table][new_pk] = {column[0]: new_value}
                    self.operations.append(('insert', table, new_pk, {column[0]: new_value}))
                    return type('Rows', (), {'rows_count': 1, 'data': [self.data[table][new_pk]]})()
        else: # UPDATE
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
        if table not in self.data: return 0
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
    print("Recovery Test - Scenario C (All Committed)")
    print("="*70)
    print("\n📋 Database Schema:")
    print("  • student(StudentID, FullName, GPA)")
    print("  • course(CourseID, Year, CourseName, CourseDescription)")
    print("  • attends(StudentID, CourseID, Year)")
    
    log_dir = "test_recovery_logs_c"
    os.makedirs(log_dir, exist_ok=True)
    
    # Clean up old logs
    for f in os.listdir(log_dir):
        try: os.remove(os.path.join(log_dir, f))
        except: pass
    
    # Initialize FRM
    buffer_mgr = MockBufferManager()
    storage_engine = MockStorageEngine()
    
    # [UPDATED] Menggunakan Callback Pattern
    frm = FailureRecoveryManager(
        buffer_manager=buffer_mgr, 
        read_disk_callback=storage_engine.read_block,
        save_disk_callback=storage_engine.write_block,
        log_directory=log_dir
    )
    
    print("\n" + "="*70)
    print("PHASE 1: Normal Operations (Before Crash)")
    print("="*70)
    
    # TX 501: START → INSERT student
    print("\n[TX 501] Starting transaction...")
    frm.notify_transaction_start(501)
    frm.write_log_entry(501, WalAction.START)
    
    print("[TX 501] INSERT operation on student")
    frm.log_write(
        tx_id=501,
        table="student",
        pk={"StudentID": 99501},
        old_data=None,
        new_data={"StudentID": 99501, "FullName": "Grace Test", "GPA": 3.9}
    )
    
    # TX 502: START → UPDATE student
    print("\n[TX 502] Starting transaction...")
    frm.notify_transaction_start(502)
    frm.write_log_entry(502, WalAction.START)
    
    print("[TX 502] UPDATE operation on student")
    frm.log_write(
        tx_id=502,
        table="student",
        pk={"StudentID": 99502},
        old_data={"StudentID": 99502, "FullName": "Henry Test", "GPA": 3.3},
        new_data={"StudentID": 99502, "FullName": "Henry Test", "GPA": 3.7}
    )
    
    # TX 503: START → DELETE student
    print("\n[TX 503] Starting transaction...")
    frm.notify_transaction_start(503)
    frm.write_log_entry(503, WalAction.START)
    
    print("[TX 503] DELETE operation on student")
    frm.log_write(
        tx_id=503,
        table="student",
        pk={"StudentID": 99503},
        old_data={"StudentID": 99503, "FullName": "Ivy Test", "GPA": 3.4},
        new_data=None
    )
    
    # CHECKPOINT
    print("\n" + "="*70)
    print("CHECKPOINT: Saving state...")
    print("="*70)
    ongoing_txs = list(frm.active_transactions)
    frm.save_checkpoint(ongoing_txs)
    print(f"Checkpoint saved with ongoing transactions: {ongoing_txs}")
    
    # After checkpoint - add more operations
    print("\n[TX 501] Additional UPDATE after checkpoint (student)")
    frm.log_write(
        tx_id=501,
        table="student",
        pk={"StudentID": 99501},
        old_data={"StudentID": 99501, "FullName": "Grace Test", "GPA": 3.9},
        new_data={"StudentID": 99501, "FullName": "Grace Test", "GPA": 4.0}
    )
    
    print("[TX 502] Additional UPDATE after checkpoint (student)")
    frm.log_write(
        tx_id=502,
        table="student",
        pk={"StudentID": 99502},
        old_data={"StudentID": 99502, "FullName": "Henry Test", "GPA": 3.7},
        new_data={"StudentID": 99502, "FullName": "Henry Test", "GPA": 3.8}
    )
    
    print("[TX 503] Additional INSERT after checkpoint (course)")
    frm.log_write(
        tx_id=503,
        table="course",
        pk={"CourseID": 99503},
        old_data=None,
        new_data={"CourseID": 99503, "Year": 2025, "CourseName": "Recovery Systems", "CourseDescription": "Advanced database recovery techniques"}
    )
    
    # ALL COMMIT
    print("\n[TX 501] Committing...")
    frm.write_log_entry(501, WalAction.COMMIT)
    frm.notify_transaction_end(501)
    
    print("[TX 502] Committing...")
    frm.write_log_entry(502, WalAction.COMMIT)
    frm.notify_transaction_end(502)
    
    print("[TX 503] Committing...")
    frm.write_log_entry(503, WalAction.COMMIT)
    frm.notify_transaction_end(503)
    
    print("\n" + "="*70)
    print("💥 SYSTEM CRASH! 💥")
    print("="*70)
    print("System restarting...\n")
    
    # Recovery
    print("="*70)
    print("PHASE 2: Recovery After Crash")
    print("="*70)
    
    # [UPDATED] Menggunakan Callback Pattern untuk instance recovery
    frm_recovery = FailureRecoveryManager(
        buffer_manager=buffer_mgr, 
        read_disk_callback=storage_engine.read_block,
        save_disk_callback=storage_engine.write_block,
        log_directory=log_dir
    )
    stats = frm_recovery.recover()
    
    # Verification
    print("\n" + "="*70)
    print("PHASE 3: Verification")
    print("="*70)
    
    print("\n[EXPECTED BEHAVIOR - All Committed Scenario]")
    print("-" * 70)
    print("✓ Checkpoint found with TX [501, 502, 503]")
    print("✓ REDO phase (operations after checkpoint):")
    print("  - TX 501 UPDATE student (GPA: 3.9 → 4.0) - committed ✓")
    print("  - TX 502 UPDATE student (GPA: 3.7 → 3.8) - committed ✓")
    print("  - TX 503 INSERT course - committed ✓")
    print("✓ After REDO, undo_list should be EMPTY")
    print("  (All transactions committed)")
    print("✓ UNDO phase:")
    print("  - No operations to undo!")
    print("  - No CLR written")
    print("  - No ABORT written")
    
    print("\n[ACTUAL RESULTS]")
    print("-" * 70)
    print(f"Checkpoint found: {stats['checkpoint_found']}")
    print(f"Checkpoint transactions: {stats['checkpoint_transactions']}")
    print(f"REDO operations: {stats['redo_count']}")
    print(f"UNDO operations: {stats['undo_count']}")
    print(f"Final undo_list (should be []): {stats.get('undo_list_final', 'N/A')}")
    
    # Assertions
    print("\n[VALIDATION]")
    print("-" * 70)
    
    try:
        assert stats['checkpoint_found'], "❌ Should find checkpoint!"
        assert 501 in stats['checkpoint_transactions'], "❌ TX 501 should be in checkpoint!"
        assert 502 in stats['checkpoint_transactions'], "❌ TX 502 should be in checkpoint!"
        assert 503 in stats['checkpoint_transactions'], "❌ TX 503 should be in checkpoint!"
        assert stats['redo_count'] == 3, f"❌ Should REDO 3 operations, got {stats['redo_count']}"
        assert stats['undo_count'] == 0, f"❌ Should UNDO 0 operations (all committed), got {stats['undo_count']}"
        assert len(stats.get('undo_list_final', [])) == 0, f"❌ undo_list should be empty!"
        
        print("✅ All validations passed!")
    except AssertionError as e:
        print(f"{e}")
        print("\n⚠️  Some validations failed - check recovery logic")
    
    print("\n" + "="*70)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("="*70)

if __name__ == "__main__":
    main()