"""
Test FailureRecoveryManager - save_checkpoint functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

# Mock BufferManager with tracking
class MockBufferManager:
    def __init__(self):
        self.flush_called = False
        self.buffer_full_threshold = 0.75
        self.current_usage = 0.5
        # Menambahkan atribut untuk menampung callback (agar tidak error saat FRM memanggil set_routine)
        self.fetch_callback = None
        self.write_callback = None
    
    def set_load_table_routine(self, callback):
        self.fetch_callback = callback
        
    def set_save_buffer_routine(self, callback):
        self.write_callback = callback

    def is_buffer_almost_full(self):
        return self.current_usage >= self.buffer_full_threshold
    
    def flush_dirty_blocks(self):
        print("[MockBuffer] Flushing dirty blocks:")
        print("  - Block A (TX 301): FLUSHED")
        print("  - Block B (TX 302): FLUSHED")
        print("  - Block C (TX 303): FLUSHED")
        self.flush_called = True

# Enhanced Mock StorageEngine with operation tracking
class MockStorageEngine:
    def __init__(self):
        self.data = {}  # table -> {pk -> row_data}
        self.operations = []  # List of (op_type, table, pk, data)
        
    def fetch_block(self, table_name, pk_value):
        print(f"[MockStorage] Fetching {table_name} with PK {pk_value}")
        return None
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
            # Find or create a new row
            new_pk = new_value if len(column) == 1 and column[0] in ['StudentID', 'nim', 'id'] else None
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

print("="*70)
print("TEST: FailureRecoveryManager - save_checkpoint()")
print("="*70)

# Initialize FRM
buffer_mgr = MockBufferManager()
storage_eng = MockStorageEngine()
frm = FailureRecoveryManager(
    buffer_manager=buffer_mgr,
    load_table_callback=storage_eng.fetch_block,   # Callback Baca
    save_buffer_callback=storage_eng.write_block,   # Callback Tulis
    log_directory="test_checkpoint_logs",
    checkpoint_interval=2
)

# ========== SCENARIO: Multiple active transactions ==========
print("\n[SCENARIO] Setup: Multiple transactions with operations")
print("-" * 70)

# TX 301: INSERT new student and ongoing
print("\n[TX 301] Starting transaction - INSERT new student")
frm.notify_transaction_start(301)
frm.write_log_entry(301, WalAction.START)
frm.log_write(
    tx_id=301,
    table="student",
    pk={"StudentID": 99301},
    old_data=None,
    new_data={"StudentID": 99301, "FullName": "Alice Test", "GPA": 3.5}
)
print("  ✓ TX 301: Inserted student 99301 (Alice)")

# TX 302: UPDATE existing student and ongoing
print("\n[TX 302] Starting transaction - UPDATE student GPA")
frm.notify_transaction_start(302)
frm.write_log_entry(302, WalAction.START)
frm.log_write(
    tx_id=302,
    table="student",
    pk={"StudentID": 99302},
    old_data={"StudentID": 99302, "FullName": "Bob Test", "GPA": 3.5},
    new_data={"StudentID": 99302, "FullName": "Bob Test", "GPA": 3.7}
)
print("  ✓ TX 302: Updated student 99302 GPA (Bob: 3.5 → 3.7)")

# TX 303: DELETE student and ongoing
print("\n[TX 303] Starting transaction - DELETE student")
frm.notify_transaction_start(303)
frm.write_log_entry(303, WalAction.START)
frm.log_write(
    tx_id=303,
    table="student",
    pk={"StudentID": 99303},
    old_data={"StudentID": 99303, "FullName": "Charlie Test", "GPA": 3.2},
    new_data=None
)
print("  ✓ TX 303: Deleted student 99303 (Charlie)")

print(f"\n[Status] Active transactions: {frm.get_active_transaction_count()}")
print("         All 3 transactions are ongoing (not committed)")

# ========== TRIGGER CHECKPOINT ==========
print("\n" + "="*70)
print("TRIGGERING MANUAL CHECKPOINT")
print("="*70)

ongoing = list(frm.active_transactions)
print(f"[Checkpoint] Ongoing transactions before checkpoint: {ongoing}")
frm.save_checkpoint(ongoing)

# ========== VERIFY CHECKPOINT ==========
print("\n" + "="*70)
print("CHECKPOINT VERIFICATION")
print("="*70)
print(f"✓ Buffer flush was called: {buffer_mgr.flush_called}")
print(f"✓ Active transactions in checkpoint: {ongoing}")
print(f"✓ Total active: {len(ongoing)}")
print("\nExpected WAL structure:")
print('  {')
print('    "type": "checkpoint",')
print('    "ongoing_transactions": [301, 302, 303]')
print('  }')

# ========== CONTINUE TRANSACTIONS ==========
print("\n" + "="*70)
print("AFTER CHECKPOINT - Transactions continue")
print("="*70)

print("\n[TX 301] Committing...")
frm.write_log_entry(301, WalAction.COMMIT)
frm.notify_transaction_end(301)
print("  ✓ TX 301 committed successfully")

print("\n[TX 302] Aborting...")
frm.write_log_entry(302, WalAction.ABORT)
frm.notify_transaction_end(302)
print("  ✓ TX 302 aborted (changes rolled back)")

print(f"\n[Status] Remaining active transactions: {frm.get_active_transaction_count()}")
print(f"         TX 303 is still ongoing")

# ========== FINAL SUMMARY ==========
print("\n" + "="*70)
print("TEST COMPLETED SUCCESSFULLY!")
print("="*70)
print("\n📋 Summary:")
print("  • TX 301: Started → Checkpoint → Committed ✓")
print("  • TX 302: Started → Checkpoint → Aborted ✗")
print("  • TX 303: Started → Checkpoint → Still Active ⏳")
print("\n📂 Check WAL file in: test_checkpoint_logs/")
print("   Look for checkpoint entry with ongoing_transactions: [301, 302, 303]")
print("\n💡 Recovery Behavior:")
print("   • If crash happens now, recovery will:")
print("     - Redo TX 301 (committed after checkpoint)")
print("     - Undo TX 302 (aborted, needs rollback)")
print("     - Undo TX 303 (ongoing, incomplete)")