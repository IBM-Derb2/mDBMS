import os
from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

class MockBufferManager:
    def is_buffer_almost_full(self):
        return False
    
    def flush_dirty_blocks(self):
        print("[MockBuffer] Flushing all dirty blocks...")

class MockStorageEngine:
    pass

def main():
    print("="*60)
    print("Recovery Test - Scenario B (No Checkpoint)")
    print("="*60)
    
    log_dir = "test_recovery_logs_b"
    os.makedirs(log_dir, exist_ok=True)
    
    # Clean up old logs
    for f in os.listdir(log_dir):
        os.remove(os.path.join(log_dir, f))
    
    # Initialize FRM
    buffer_mgr = MockBufferManager()
    storage_engine = MockStorageEngine()
    frm = FailureRecoveryManager(buffer_mgr, storage_engine, log_dir)
    
    print("\n" + "="*60)
    print("PHASE 1: Normal Operations (No Checkpoint)")
    print("="*60)
    
    # TODO: Implement scenario
    # T401: START → INSERT → COMMIT
    print("\n[TX 401] Starting transaction...")
    frm.notify_transaction_start(401)
    frm.write_log_entry(401, WalAction.START)
    
    print("[TX 401] INSERT operation")
    frm.log_write(
        tx_id=401,
        table="mahasiswa",
        pk={"nim": "13520401"},
        old_data=None,
        new_data={"nim": "13520401", "nama": "David", "ipk": 3.7}
    )
    
    # T402: START → UPDATE → ABORT
    print("\n[TX 402] Starting transaction...")
    frm.notify_transaction_start(402)
    frm.write_log_entry(402, WalAction.START)
    
    print("[TX 402] UPDATE operation")
    frm.log_write(
        tx_id=402,
        table="mahasiswa",
        pk={"nim": "13520402"},
        old_data={"nim": "13520402", "nama": "Eve", "ipk": 3.2},
        new_data={"nim": "13520402", "nama": "Eve", "ipk": 3.8}
    )
    
    # T403: START → DELETE → CRASH (no commit/abort)
    print("\n[TX 403] Starting transaction...")
    frm.notify_transaction_start(403)
    frm.write_log_entry(403, WalAction.START)
    
    print("[TX 403] DELETE operation")
    frm.log_write(
        tx_id=403,
        table="mahasiswa",
        pk={"nim": "13520403"},
        old_data={"nim": "13520403", "nama": "Frank", "ipk": 3.5},
        new_data=None
    )
    
    # T401: COMMIT
    print("\n[TX 401] Committing...")
    frm.write_log_entry(401, WalAction.COMMIT)
    frm.notify_transaction_end(401)
    
    # T402: ABORT
    print("\n[TX 402] Aborting...")
    frm.write_log_entry(402, WalAction.ABORT)
    frm.abort_transaction(402)
    frm.notify_transaction_end(402)
    
    # T403: CRASH - no commit/abort
    print("\n[TX 403] Still ongoing (crash!)...")
    
    print("\n" + "="*60)
    print("💥 SYSTEM CRASH! 💥")
    print("="*60)
    print("System restarting...\n")
    
    # Recovery
    print("="*60)
    print("PHASE 2: Recovery After Crash")
    print("="*60)
    
    frm_recovery = FailureRecoveryManager(buffer_mgr, storage_engine, log_dir)
    stats = frm_recovery.recover()
    
    # Verification
    print("\n" + "="*60)
    print("PHASE 3: Verification")
    print("="*60)
    
    print("\n[EXPECTED BEHAVIOR - No Checkpoint Scenario]")
    print("-" * 60)
    print("✓ No checkpoint found")
    print("✓ Recovery starts from BEGINNING of log")
    print("✓ REDO phase:")
    print("  - T401 INSERT (committed)")
    print("  - T402 UPDATE (aborted, but still REDO)")
    print("  - T403 DELETE (incomplete)")
    print("✓ After REDO, undo_list should contain: T403 only")
    print("✓ UNDO phase:")
    print("  - Undo T403 DELETE → Re-insert Frank")
    print("  - Write CLR for T403")
    print("  - Write ABORT for T403")
    
    print("\n[ACTUAL RESULTS]")
    print("-" * 60)
    print(f"Checkpoint found: {stats['checkpoint_found']}")
    print(f"Checkpoint transactions: {stats['checkpoint_transactions']}")
    print(f"REDO operations: {stats['redo_count']}")
    print(f"UNDO operations: {stats['undo_count']}")
    print(f"Final undo_list (should be []): {stats['undo_list_final']}")
    
    # Assertions
    print("\n[VALIDATION]")
    print("-" * 60)
    
    assert not stats['checkpoint_found'], "❌ Should NOT find checkpoint!"
    assert stats['checkpoint_transactions'] == [], "❌ Checkpoint transactions should be empty!"
    assert stats['redo_count'] == 3, f"❌ Should REDO 3 operations, got {stats['redo_count']}"
    assert stats['undo_count'] == 1, f"❌ Should UNDO 1 operation (T403), got {stats['undo_count']}"
    assert len(stats['undo_list_final']) == 0, f"❌ undo_list should be empty after recovery!"
    
    print("✅ All validations passed!")
    print("\n" + "="*60)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("="*60)
    
    # Check for CLR
    print("\n[BONUS] Checking for Compensation Logs...")
    from log_parser import LogParser
    parser = LogParser(log_dir)
    
    clr_count = 0
    for entry in parser.iter_backward():
        if entry.action == "clr":
            clr_count += 1
            print(f"✓ Found CLR for TX {entry.transaction_id} (original: {entry.raw_log.get('original_action')})")
    
    if clr_count > 0:
        print(f"✅ Found {clr_count} CLR(s) - Compensation logging is working!")
    else:
        print("⚠️  No CLR found")

if __name__ == "__main__":
    main()