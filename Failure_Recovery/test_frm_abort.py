"""
Test FailureRecoveryManager - abort_transaction functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

# Mock managers
class MockBufferManager:
    def is_buffer_almost_full(self):
        return False

class MockStorageEngine:
    pass

print("="*70)
print("TEST: FailureRecoveryManager - abort_transaction()")
print("="*70)

# Initialize FRM
buffer_mgr = MockBufferManager()
storage_eng = MockStorageEngine()
frm = FailureRecoveryManager(
    buffer_manager=buffer_mgr,
    storage_engine=storage_eng,
    log_directory="test_abort_logs"
)

# ========== TEST SCENARIO ==========
# TX 201 does multiple operations then ABORTS
# Expected: All operations should be undone

print("\n[SCENARIO] TX 201: Multiple operations then ABORT")
print("-" * 70)

# Start transaction
frm.notify_transaction_start(201)
frm.write_log_entry(201, WalAction.START)

# Operation 1: INSERT
print("\n[OP 1] INSERT new student")
frm.log_write(
    tx_id=201,
    table="mahasiswa",
    pk={"nim": "13520999"},
    old_data=None,
    new_data={"nim": "13520999", "nama": "Alice", "ipk": 3.5}
)

# Operation 2: UPDATE 
print("\n[OP 2] UPDATE student IPK")
frm.log_write(
    tx_id=201,
    table="mahasiswa",
    pk={"nim": "13520999"},
    old_data={"nim": "13520999", "nama": "Alice", "ipk": 3.5},
    new_data={"nim": "13520999", "nama": "Alice", "ipk": 3.7}
)

# Operation 3: DELETE another student
print("\n[OP 3] DELETE another student")
frm.log_write(
    tx_id=201,
    table="mahasiswa",
    pk={"nim": "13520001"},
    old_data={"nim": "13520001", "nama": "Budi", "ipk": 3.8},
    new_data=None
)

# Transaction ABORTS!
print("\n" + "="*70)
print("[ABORT] TX 201 is aborting - need to rollback!")
print("="*70)

frm.write_log_entry(201, WalAction.ABORT)

# Call abort_transaction to rollback
frm.abort_transaction(201)

frm.notify_transaction_end(201)

print("\n" + "="*70)
print("TEST COMPLETED!")
print("="*70)
print("\nExpected undo operations (in reverse order):")
print("1. Undo DELETE: Re-insert Budi")
print("2. Undo UPDATE: Restore Alice IPK to 3.5")
print("3. Undo INSERT: Delete Alice")
print("\nCheck logs above to verify!")