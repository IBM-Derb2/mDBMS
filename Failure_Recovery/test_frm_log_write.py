"""
Test FailureRecoveryManager - log_write functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

# Mock BufferManager for testing
class MockBufferManager:
    def is_buffer_almost_full(self):
        return False  # Not full yet

# Mock StorageEngine for testing
class MockStorageEngine:
    pass

print("="*70)
print("TEST: FailureRecoveryManager - log_write()")
print("="*70)

# Initialize FRM
buffer_mgr = MockBufferManager()
storage_eng = MockStorageEngine()
frm = FailureRecoveryManager(
    buffer_manager=buffer_mgr,
    storage_engine=storage_eng,
    log_directory="test_wal_logs"
)

# Test 1: INSERT operation
print("\n[TEST 1] Testing INSERT operation")
frm.notify_transaction_start(101)
frm.write_log_entry(101, WalAction.START)

frm.log_write(
    tx_id=101,
    table="mahasiswa",
    pk={"nim": "13520001"},
    old_data=None,  # INSERT - no old data
    new_data={"nim": "13520001", "nama": "Budi", "ipk": 3.8}
)

frm.write_log_entry(101, WalAction.COMMIT)
frm.notify_transaction_end(101)

# Test 2: UPDATE operation
print("\n[TEST 2] Testing UPDATE operation")
frm.notify_transaction_start(102)
frm.write_log_entry(102, WalAction.START)

frm.log_write(
    tx_id=102,
    table="mahasiswa",
    pk={"nim": "13520001"},
    old_data={"nim": "13520001", "nama": "Budi", "ipk": 3.8},
    new_data={"nim": "13520001", "nama": "Budi", "ipk": 3.9}
)

frm.write_log_entry(102, WalAction.COMMIT)
frm.notify_transaction_end(102)

# Test 3: DELETE operation
print("\n[TEST 3] Testing DELETE operation")
frm.notify_transaction_start(103)
frm.write_log_entry(103, WalAction.START)

frm.log_write(
    tx_id=103,
    table="mahasiswa",
    pk={"nim": "13520001"},
    old_data={"nim": "13520001", "nama": "Budi", "ipk": 3.9},
    new_data=None  # DELETE - no new data
)

frm.write_log_entry(103, WalAction.COMMIT)
frm.notify_transaction_end(103)

print("\n" + "="*70)
print("TEST COMPLETED!")
print("="*70)
print(f"\nCheck WAL file in: test_wal_logs/")
print("Active transactions:", frm.get_active_transaction_count())