import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

# Mock BufferManager
class MockBufferManager:
    def is_buffer_almost_full(self):
        return False
    
    def flush_dirty_blocks(self):
        print("[MockBuffer] Flushing all dirty blocks...")

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
            pk_columns = {
                'student': 'StudentID',
                'course': 'CourseID',
                'attends': 'StudentID'
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
        table = data_retrieval.table
        conditions = data_retrieval.conditions
        
        if table not in self.data:
            return type('Rows', (), {'rows_count': 0, 'data': []})()
        
        pk_value = None
        for cond in conditions:
            if hasattr(cond, 'column') and hasattr(cond, 'value'):
                pk_value = cond.value
                break
        
        if pk_value and pk_value in self.data[table]:
            return type('Rows', (), {'rows_count': 1, 'data': [self.data[table][pk_value]]})()
        
        return type('Rows', (), {'rows_count': 0, 'data': []})()

def main():
    print("="*70)
    print("Recovery Test - Scenario B (No Checkpoint)")
    print("="*70)
    print("\n📋 Database Schema:")
    print("  • student(StudentID, FullName, GPA)")
    print("  • course(CourseID, Year, CourseName, CourseDescription)")
    print("  • attends(StudentID, CourseID, Year)")
    
    log_dir = "test_recovery_logs_b"
    os.makedirs(log_dir, exist_ok=True)
    
    # Clean up old logs
    for f in os.listdir(log_dir):
        os.remove(os.path.join(log_dir, f))
    
    # Initialize FRM
    buffer_mgr = MockBufferManager()
    storage_engine = MockStorageEngine()
    frm = FailureRecoveryManager(buffer_mgr, storage_engine, log_dir)
    
    print("\n" + "="*70)
    print("PHASE 1: Normal Operations (No Checkpoint)")
    print("="*70)
    
    # TX 401: START → INSERT → COMMIT
    print("\n[TX 401] Starting transaction...")
    frm.notify_transaction_start(401)
    frm.write_log_entry(401, WalAction.START)
    
    print("[TX 401] INSERT operation on student")
    frm.log_write(
        tx_id=401,
        table="student",
        pk={"StudentID": 99401},
        old_data=None,  # INSERT
        new_data={"StudentID": 99401, "FullName": "David Test", "GPA": 3.7}
    )
    
    # TX 402: START → UPDATE → ABORT
    print("\n[TX 402] Starting transaction...")
    frm.notify_transaction_start(402)
    frm.write_log_entry(402, WalAction.START)
    
    print("[TX 402] UPDATE operation on student")
    frm.log_write(
        tx_id=402,
        table="student",
        pk={"StudentID": 99402},
        old_data={"StudentID": 99402, "FullName": "Eve Test", "GPA": 3.2},
        new_data={"StudentID": 99402, "FullName": "Eve Test", "GPA": 3.8}
    )
    
    # TX 403: START → DELETE → CRASH (no commit/abort)
    print("\n[TX 403] Starting transaction...")
    frm.notify_transaction_start(403)
    frm.write_log_entry(403, WalAction.START)
    
    print("[TX 403] DELETE operation on student")
    frm.log_write(
        tx_id=403,
        table="student",
        pk={"StudentID": 99403},
        old_data={"StudentID": 99403, "FullName": "Frank Test", "GPA": 3.5},
        new_data=None  # DELETE
    )
    
    # TX 401: COMMIT
    print("\n[TX 401] Committing...")
    frm.write_log_entry(401, WalAction.COMMIT)
    frm.notify_transaction_end(401)
    
    # TX 402: ABORT
    print("\n[TX 402] Aborting...")
    frm.write_log_entry(402, WalAction.ABORT)
    frm.abort_transaction(402)
    frm.notify_transaction_end(402)
    
    # TX 403: CRASH - no commit/abort
    print("\n[TX 403] Still ongoing (crash!)...")
    
    print("\n" + "="*70)
    print("💥 SYSTEM CRASH! 💥")
    print("="*70)
    print("System restarting...\n")
    
    # Recovery
    print("="*70)
    print("PHASE 2: Recovery After Crash")
    print("="*70)
    
    frm_recovery = FailureRecoveryManager(buffer_mgr, storage_engine, log_dir)
    stats = frm_recovery.recover()
    
    # Verification
    print("\n" + "="*70)
    print("PHASE 3: Verification")
    print("="*70)
    
    print("\n[EXPECTED BEHAVIOR - No Checkpoint Scenario]")
    print("-" * 70)
    print("✓ No checkpoint found")
    print("✓ Recovery starts from BEGINNING of log")
    print("✓ REDO phase:")
    print("  - TX 401 INSERT student (committed) ✓")
    print("  - TX 402 UPDATE student (aborted, but still REDO) ✗")
    print("  - TX 403 DELETE student (incomplete) ⏳")
    print("✓ After REDO, undo_list should contain: TX 403 only")
    print("  (TX 401 committed, TX 402 explicitly aborted)")
    print("✓ UNDO phase:")
    print("  - Undo TX 403 DELETE → Re-insert Frank")
    print("  - Write CLR for TX 403")
    print("  - Write ABORT for TX 403")
    
    print("\n[ACTUAL RESULTS]")
    print("-" * 70)
    print(f"Checkpoint found: {stats['checkpoint_found']}")
    print(f"Checkpoint transactions: {stats['checkpoint_transactions']}")
    print(f"REDO operations: {stats['redo_count']}")
    print(f"UNDO operations: {stats['undo_count']}")
    print(f"Incomplete transactions (should be []): {stats.get('undo_list_final', 'N/A')}")
    
    # Assertions
    print("\n[VALIDATION]")
    print("-" * 70)
    
    try:
        assert not stats['checkpoint_found'], "❌ Should NOT find checkpoint!"
        assert stats['checkpoint_transactions'] == [], "❌ Checkpoint transactions should be empty!"
        assert stats['redo_count'] == 3, f"❌ Should REDO 3 operations, got {stats['redo_count']}"
        assert stats['undo_count'] == 1, f"❌ Should UNDO 1 operation (TX 403), got {stats['undo_count']}"
        assert len(stats.get('undo_list_final', [])) == 0, f"❌ undo_list should be empty after recovery!"
        
        print("✅ All validations passed!")
    except AssertionError as e:
        print(f"{e}")
        print("\n⚠️  Some validations failed - check recovery logic")
    
    print("\n" + "="*70)
    print("TEST COMPLETED!")
    print("="*70)
    
    # Check for CLR
    print("\n[BONUS] Checking for Compensation Logs...")
    from log_parser import LogParser
    parser = LogParser(log_dir)
    
    clr_count = 0
    for entry in parser.iter_backward():
        if entry.action == "clr":
            clr_count += 1
            print(f"✓ Found CLR for TX {entry.transaction_id}")
            print(f"  - Original action: {entry.raw_log.get('original_action', 'N/A')}")
            print(f"  - Table: {entry.table_name}")
            print(f"  - PK: {entry.pk_value}")
    
    if clr_count > 0:
        print(f"\n✅ Found {clr_count} CLR(s) - Compensation logging is working!")
    else:
        print("\n⚠️  No CLR found (check _write_compensation_log implementation)")
    
    print(f"\n📂 Log files saved in: {log_dir}/")
    
    # Summary table
    print("\n" + "="*70)
    print("FINAL STATE SUMMARY")
    print("="*70)
    print("\n┌─────────┬──────────────────────────┬─────────────┬──────────────┐")
    print("│ TX ID   │ Operations               │ Outcome     │ Final Effect │")
    print("├─────────┼──────────────────────────┼─────────────┼──────────────┤")
    print("│ 401     │ INSERT student           │ COMMIT      │ KEPT ✓       │")
    print("├─────────┼──────────────────────────┼─────────────┼──────────────┤")
    print("│ 402     │ UPDATE student           │ ABORT       │ UNDONE ✗     │")
    print("├─────────┼──────────────────────────┼─────────────┼──────────────┤")
    print("│ 403     │ DELETE student           │ CRASH       │ UNDONE ✗     │")
    print("└─────────┴──────────────────────────┴─────────────┴──────────────┘")
    print("\n💡 Key Difference from Scenario A:")
    print("   • No checkpoint → Recovery scans ENTIRE log from beginning")
    print("   • All operations (before/after non-existent checkpoint) are REDOne")
    print("   • Incomplete TX 403 is UNDOne completely")

if __name__ == "__main__":
    main()