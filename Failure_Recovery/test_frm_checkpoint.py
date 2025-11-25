"""
Test FailureRecoveryManager - save_checkpoint functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

# Mock BufferManager with tracking
class MockBufferManager:
    def __init__(self):
        self.flush_called = False
        self.buffer_full_threshold = 0.75
        self.current_usage = 0.5
    
    def is_buffer_almost_full(self):
        return self.current_usage >= self.buffer_full_threshold
    
    def flush_dirty_blocks(self):
        print("[MockBuffer] Flushing dirty blocks:")
        print("  - Block A (TX 301): FLUSHED")
        print("  - Block B (TX 302): FLUSHED")
        print("  - Block C (TX 303): FLUSHED")
        self.flush_called = True

class MockStorageEngine:
    pass

print("="*70)
print("TEST: FailureRecoveryManager - save_checkpoint()")
print("="*70)

# Initialize FRM
buffer_mgr = MockBufferManager()
storage_eng = MockStorageEngine()
frm = FailureRecoveryManager(
    buffer_manager=buffer_mgr,
    storage_engine=storage_eng,
    log_directory="test_checkpoint_logs",
    checkpoint_interval=2  # 2 seconds for testing
)

# ========== SCENARIO: Multiple active transactions ==========
print("\n[SCENARIO] Setup: Multiple transactions with operations")
print("-" * 70)

# TX 301: INSERT and ongoing
frm.notify_transaction_start(301)
frm.write_log_entry(301, WalAction.START)
frm.log_write(301, "mahasiswa", {"nim": "301"}, None, {"nim": "301", "nama": "Alice"})

# TX 302: UPDATE and ongoing
frm.notify_transaction_start(302)
frm.write_log_entry(302, WalAction.START)
frm.log_write(302, "mahasiswa", {"nim": "302"}, 
              {"nim": "302", "nama": "Bob", "ipk": 3.5},
              {"nim": "302", "nama": "Bob", "ipk": 3.7})

# TX 303: DELETE and ongoing
frm.notify_transaction_start(303)
frm.write_log_entry(303, WalAction.START)
frm.log_write(303, "mahasiswa", {"nim": "303"},
              {"nim": "303", "nama": "Charlie"}, None)

print(f"\nActive transactions: {frm.get_active_transaction_count()}")
print("All 3 transactions are ongoing (not committed)")

# ========== TRIGGER CHECKPOINT ==========
print("\n" + "="*70)
print("TRIGGERING MANUAL CHECKPOINT")
print("="*70)

ongoing = list(frm.active_transactions)
frm.save_checkpoint(ongoing)

# ========== VERIFY CHECKPOINT ==========
print("\n[VERIFICATION]")
print(f"Buffer flush was called: {buffer_mgr.flush_called}")
print(f"Active transactions in checkpoint: {ongoing}")
print("\nExpected WAL structure:")
print('  {"type": "checkpoint", "ongoing_transactions": [301, 302, 303]}')

# ========== CONTINUE TRANSACTIONS ==========
print("\n[SCENARIO] After checkpoint - transactions continue")
frm.write_log_entry(301, WalAction.COMMIT)
frm.notify_transaction_end(301)
print("TX 301 committed")

frm.write_log_entry(302, WalAction.ABORT)
frm.notify_transaction_end(302)
print("TX 302 aborted")

print(f"\nRemaining active transactions: {frm.get_active_transaction_count()}")

print("\n" + "="*70)
print("TEST COMPLETED!")
print("="*70)
print("\nCheck WAL file in: test_checkpoint_logs/")
print("Look for checkpoint entry with ongoing_transactions")