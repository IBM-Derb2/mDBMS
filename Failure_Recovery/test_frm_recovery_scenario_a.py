import os
import json
from datetime import datetime
from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

# Mock classes (same as checkpoint test)
class MockBufferManager:
    def is_buffer_almost_full(self):
        return False
    
    def flush_dirty_blocks(self):
        print("[MockBuffer] Flushing all dirty blocks...")

class MockStorageEngine:
    pass

def main():
    print("="*60)
    print("Recovery Test - Scenario A")
    print("="*60)
    
    log_dir = "test_recovery_logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Clean up old logs
    for f in os.listdir(log_dir):
        os.remove(os.path.join(log_dir, f))
    
    # Initialize FRM
    buffer_mgr = MockBufferManager()
    storage_engine = MockStorageEngine()
    frm = FailureRecoveryManager(buffer_mgr, storage_engine, log_dir)
    
    print("\n" + "="*60)
    print("PHASE 1: Normal Operations (Before Crash)")
    print("="*60)
    
    # TX 301: START → INSERT → (will COMMIT after checkpoint)
    print("\n[TX 301] Starting transaction...")
    frm.notify_transaction_start(301)
    frm.write_log_entry(301, WalAction.START)
    
    print("[TX 301] INSERT operation")
    frm.log_write(
        tx_id=301,
        table="mahasiswa",
        pk={"nim": "13520301"},
        old_data=None,  # INSERT
        new_data={"nim": "13520301", "nama": "Alice", "ipk": 3.8}
    )
    
    # TX 302: START → UPDATE → (will ABORT after checkpoint)
    print("\n[TX 302] Starting transaction...")
    frm.notify_transaction_start(302)
    frm.write_log_entry(302, WalAction.START)
    
    print("[TX 302] UPDATE operation")
    frm.log_write(
        tx_id=302,
        table="mahasiswa",
        pk={"nim": "13520302"},
        old_data={"nim": "13520302", "nama": "Bob", "ipk": 3.5},
        new_data={"nim": "13520302", "nama": "Bob", "ipk": 3.9}  # Updated IPK
    )
    
    # TX 303: START → DELETE → (will CRASH - no COMMIT/ABORT)
    print("\n[TX 303] Starting transaction...")
    frm.notify_transaction_start(303)
    frm.write_log_entry(303, WalAction.START)
    
    print("[TX 303] DELETE operation")
    frm.log_write(
        tx_id=303,
        table="mahasiswa",
        pk={"nim": "13520303"},
        old_data={"nim": "13520303", "nama": "Charlie", "ipk": 3.6},
        new_data=None  # DELETE
    )
    
    #  CHECKPOINT [301, 302, 303]
    print("\n" + "="*60)
    print("CHECKPOINT: Saving state...")
    print("="*60)
    ongoing_txs = list(frm.active_transactions)
    frm.save_checkpoint(ongoing_txs)
    print(f"Checkpoint saved with ongoing transactions: {ongoing_txs}")

    # ⭐ AFTER CHECKPOINT - Add more operations
    print("\n[TX 301] Additional UPDATE after checkpoint")
    frm.log_write(
        tx_id=301,
        table="mahasiswa",
        pk={"nim": "13520301"},
        old_data={"nim": "13520301", "nama": "Alice", "ipk": 3.8},
        new_data={"nim": "13520301", "nama": "Alice", "ipk": 4.0}  # Update IPK
    )

    print("[TX 302] Additional UPDATE after checkpoint")
    frm.log_write(
        tx_id=302,
        table="mahasiswa",
        pk={"nim": "13520302"},
        old_data={"nim": "13520302", "nama": "Bob", "ipk": 3.9},
        new_data={"nim": "13520302", "nama": "Bob", "ipk": 3.7}  # Update IPK again
    )

    print("[TX 303] Additional DELETE after checkpoint")
    frm.log_write(
        tx_id=303,
        table="dosen",
        pk={"nip": "001"},
        old_data={"nip": "001", "nama": "Dr. David", "dept": "IF"},
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
    
    print("\n" + "="*60)
    print("💥 SYSTEM CRASH! 💥")
    print("="*60)
    print("System restarting...\n")
    
    # Simulate system restart - create new FRM instance
    print("="*60)
    print("PHASE 2: Recovery After Crash")
    print("="*60)
    
    frm_recovery = FailureRecoveryManager(
        buffer_mgr, 
        storage_engine, 
        log_dir
    )
    
    # Call recovery
    stats = frm_recovery.recover()
    
    # Verify results
    print("\n" + "="*60)
    print("PHASE 3: Verification")
    print("="*60)
    
    print("\n[EXPECTED BEHAVIOR]")
    print("-" * 60)
    print("✓ Checkpoint found with TX [301, 302, 303]")
    print("✓ REDO phase:")
    print("  - TX 301 INSERT (committed after checkpoint)")
    print("  - TX 302 UPDATE (aborted after checkpoint, but REDO first)")
    print("  - TX 303 DELETE (incomplete)")
    print("✓ After REDO, undo_list should contain: TX 303 only")
    print("  (TX 301 committed, TX 302 aborted)")
    print("✓ UNDO phase:")
    print("  - Undo TX 303 DELETE → Re-insert Charlie")
    print("  - Write CLR for TX 303")
    print("  - Write ABORT for TX 303")
    
    print("\n[ACTUAL RESULTS]")
    print("-" * 60)
    print(f"Checkpoint found: {stats['checkpoint_found']}")
    print(f"Checkpoint transactions: {stats['checkpoint_transactions']}")
    print(f"REDO operations: {stats['redo_count']}")
    print(f"UNDO operations: {stats['undo_count']}")
    print(f"Incomplete transactions (should be []): {stats['undo_list_final']}")
    
    # Assertions
    print("\n[VALIDATION]")
    print("-" * 60)
    
    assert stats['checkpoint_found'], "❌ Checkpoint should be found!"
    assert 301 in stats['checkpoint_transactions'], "❌ TX 301 should be in checkpoint!"
    assert 302 in stats['checkpoint_transactions'], "❌ TX 302 should be in checkpoint!"
    assert 303 in stats['checkpoint_transactions'], "❌ TX 303 should be in checkpoint!"
    assert stats['redo_count'] == 3, f"❌ Should REDO 3 operations, got {stats['redo_count']}"
    assert stats['undo_count'] == 2, f"❌ Should UNDO 1 operation (TX 303), got {stats['undo_count']}"
    assert len(stats['undo_list_final']) == 0, f"❌ undo_list should be empty after recovery!"
    
    print("✅ All validations passed!")
    print("\n" + "="*60)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("="*60)
    
    # Check for CLR in logs
    print("\n[BONUS] Checking for Compensation Logs...")
    from log_parser import LogParser
    parser = LogParser(log_dir)
    
    clr_found = False
    for entry in parser.iter_backward():
        if entry.action == "clr":
            clr_found = True
            print(f"✓ Found CLR for TX {entry.transaction_id} (original: {entry.raw_log.get('original_action')})")
            break
    
    if clr_found:
        print("✅ Compensation logging is working!")
    else:
        print("⚠️  No CLR found (check _write_compensation_log implementation)")

if __name__ == "__main__":
    main()