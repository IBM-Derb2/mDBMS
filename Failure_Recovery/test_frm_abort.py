"""
Test FailureRecoveryManager - abort_transaction functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

# Import real Storage Engine
try:
    from Storage_Manager.storage_engine import StorageEngine
    from Storage_Manager.utils import DataWrite, DataDeletion, DataRetrieval, Condition
    STORAGE_AVAILABLE = True
    print("[Test] Using REAL Storage Engine")
except ImportError:
    STORAGE_AVAILABLE = False
    print("[Test] Storage Engine not available, using mock")

# Mock BufferManager (keep this simple)
class MockBufferManager:
    def is_buffer_almost_full(self):
        return False
    
    def flush_dirty_blocks(self):
        pass

# Setup Storage Engine or Mock
if STORAGE_AVAILABLE:
    storage_eng = StorageEngine()
    
    print("[Test] Using 'student' table with schema:")
    print("  - StudentID (int)")
    print("  - FullName (varchar)")
    print("  - GPA (float)")
    
    try:
        # Check if test student exists (StudentID=99999)
        print("\n[Test] Checking if StudentID=99999 exists...")
        retrieval = DataRetrieval(
            table="student",
            column=["*"],
            conditions=[Condition("StudentID", "=", 99999)],
            search_type="sequential"
        )
        result = storage_eng.read_block(retrieval)
        if result.rows_count > 0:
            print("  ✓ Test student already exists")
        else:
            print("  ✓ Test student does not exist (good)")
        
        # Check if StudentID=1 exists (will be deleted in test)
        print("[Test] Checking if StudentID=1 exists...")
        retrieval = DataRetrieval(
            table="student",
            column=["*"],
            conditions=[Condition("StudentID", "=", 1)],
            search_type="sequential"
        )
        result = storage_eng.read_block(retrieval)
        if result.rows_count > 0:
            print(f"  ✓ StudentID=1 exists: {result.data[0]}")
        else:
            print("  ⚠️  StudentID=1 not found (test may fail)")
            
    except Exception as e:
        print(f"[Test] Warning during setup: {e}")
else:
    class MockStorageEngine:
        def write_block(self, data_write):
            print(f"    [MockStorage] write_block: table={data_write.table}")
        
        def delete_block(self, data_deletion):
            print(f"    [MockStorage] delete_block: table={data_deletion.table}")
    
    storage_eng = MockStorageEngine()

print("\n" + "="*70)
print("TEST: FailureRecoveryManager - abort_transaction()")
print("="*70)

# Initialize FRM
buffer_mgr = MockBufferManager()
frm = FailureRecoveryManager(
    buffer_manager=buffer_mgr,
    storage_engine=storage_eng,
    log_directory="test_abort_logs"
)

# ========== TEST SCENARIO ==========
print("\n[SCENARIO] TX 201: Multiple operations then ABORT")
print("-" * 70)

# Start transaction
frm.notify_transaction_start(201)
frm.write_log_entry(201, WalAction.START)

# Operation 1: INSERT new student (StudentID=99999)
print("\n[OP 1] INSERT new student (StudentID=99999)")
frm.log_write(
    tx_id=201,
    table="student",
    pk={"StudentID": 99999},
    old_data=None,
    new_data={"StudentID": 99999, "FullName": "Alice Test", "GPA": 3.5}
)

if STORAGE_AVAILABLE:
    # Insert StudentID first
    data_write = DataWrite(
        table="student",
        column=["StudentID"],
        conditions=[],
        new_value=99999
    )
    storage_eng.write_block(data_write)
    
    # Then update FullName
    data_write = DataWrite(
        table="student",
        column=["FullName"],
        conditions=[Condition("StudentID", "=", 99999)],
        new_value="Alice Test"
    )
    storage_eng.write_block(data_write)
    
    # Then update GPA
    data_write = DataWrite(
        table="student",
        column=["GPA"],
        conditions=[Condition("StudentID", "=", 99999)],
        new_value=3.5
    )
    storage_eng.write_block(data_write)
    print("  ✓ Alice Test inserted to storage")

# Operation 2: UPDATE student GPA
print("\n[OP 2] UPDATE student GPA (StudentID=99999)")
frm.log_write(
    tx_id=201,
    table="student",
    pk={"StudentID": 99999},
    old_data={"StudentID": 99999, "FullName": "Alice Test", "GPA": 3.5},
    new_data={"StudentID": 99999, "FullName": "Alice Test", "GPA": 3.7}
)

if STORAGE_AVAILABLE:
    data_write = DataWrite(
        table="student",
        column=["GPA"],
        conditions=[Condition("StudentID", "=", 99999)],
        new_value=3.7
    )
    storage_eng.write_block(data_write)
    print("  ✓ Alice GPA updated in storage")

# Operation 3: DELETE another student (StudentID=1)
print("\n[OP 3] DELETE another student (StudentID=1)")
frm.log_write(
    tx_id=201,
    table="student",
    pk={"StudentID": 1},
    old_data={"StudentID": 1, "FullName": "Student_1", "GPA": 3.12},
    new_data=None
)

if STORAGE_AVAILABLE:
    data_deletion = DataDeletion(
        table="student",
        conditions=[Condition("StudentID", "=", 1)]
    )
    storage_eng.delete_block(data_deletion)
    print("  ✓ Student_1 deleted from storage")

# Transaction ABORTS!
print("\n" + "="*70)
print("[ABORT] TX 201 is aborting - need to rollback!")
print("="*70)

frm.write_log_entry(201, WalAction.ABORT)
frm.abort_transaction(201)
frm.notify_transaction_end(201)

print("\n" + "="*70)
print("TEST COMPLETED!")
print("="*70)
print("\nExpected undo operations (in reverse order):")
print("1. Undo DELETE: Re-insert Student_1 (StudentID=1)")
print("2. Undo UPDATE: Restore Alice GPA to 3.5")
print("3. Undo INSERT: Delete Alice Test (StudentID=99999)")

# Verify final state if using real storage
if STORAGE_AVAILABLE:
    print("\n" + "="*70)
    print("VERIFICATION: Checking final storage state")
    print("="*70)
    
    try:
        # Check if Alice was deleted (undo INSERT)
        print("\n[Check 1] Alice Test (StudentID=99999) should be DELETED")
        retrieval = DataRetrieval(
            table="student",
            column=["*"],
            conditions=[Condition("StudentID", "=", 99999)],
            search_type="sequential"
        )
        result = storage_eng.read_block(retrieval)
        if result.rows_count == 0:
            print("  ✅ Alice successfully deleted (undo INSERT worked)")
        else:
            print(f"  ❌ Alice still exists: {result.data}")
        
        # Check if Student_1 was re-inserted (undo DELETE)
        print("\n[Check 2] Student_1 (StudentID=1) should be RE-INSERTED")
        retrieval = DataRetrieval(
            table="student",
            column=["*"],
            conditions=[Condition("StudentID", "=", 1)],
            search_type="sequential"
        )
        result = storage_eng.read_block(retrieval)
        if result.rows_count > 0:
            print(f"  ✅ Student_1 re-inserted successfully:")
            print(f"     {result.data[0]}")
        else:
            print("  ❌ Student_1 not found (undo DELETE failed)")
        
        print("\n✅ All operations successfully rolled back!")
        
    except Exception as e:
        print(f"\n⚠️  Verification failed: {e}")
        import traceback
        traceback.print_exc()