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
    print("Recovery Test - Scenario C (All Committed)")
    print("="*60)
    
    log_dir = "test_recovery_logs_c"
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
    
    # T501: START → INSERT
    print("\n[TX 501] Starting transaction...")
    frm.notify_transaction_start(501)
    frm.write_log_entry(501, WalAction.START)
    
    print("[TX 501] INSERT operation")
    frm.log_write(
        tx_id=501,
        table="mahasiswa",
        pk={"nim": "13520501"},
        old_data=None,
        new_data={"nim": "13520501", "nama": "Grace", "ipk": 3.9}
    )
    
    # T502: START → UPDATE
    print("\n[TX 502] Starting transaction...")
    frm.notify_transaction_start(502)
    frm.write_log_entry(502, WalAction.START)
    
    print("[TX 502] UPDATE operation")
    frm.log_write(
        tx_id=502,
        table="mahasiswa",
        pk={"nim": "13520502"},
        old_data={"nim": "13520502", "nama": "Henry", "ipk": 3.3},
        new_data={"nim": "13520502", "nama": "Henry", "ipk": 3.7}
    )
    
    # T503: START → DELETE
    print("\n[TX 503] Starting transaction...")
    frm.notify_transaction_start(503)
    frm.write_log_entry(503, WalAction.START)
    
    print("[TX 503] DELETE operation")
    frm.log_write(
        tx_id=503,
        table="mahasiswa",
        pk={"nim": "13520503"},
        old_data={"nim": "13520503", "nama": "Ivy", "ipk": 3.4},
        new_data=None
    )
    
    # CHECKPOINT
    print("\n" + "="*60)
    print("CHECKPOINT: Saving state...")
    print("="*60)
    ongoing_txs = list(frm.active_transactions)
    frm.save_checkpoint(ongoing_txs)
    print(f"Checkpoint saved with ongoing transactions: {ongoing_txs}")
    
    # After checkpoint - add more operations
    print("\n[TX 501] Additional UPDATE after checkpoint")
    frm.log_write(
        tx_id=501,
        table="mahasiswa",
        pk={"nim": "13520501"},
        old_data={"nim": "13520501", "nama": "Grace", "ipk": 3.9},
        new_data={"nim": "13520501", "nama": "Grace", "ipk": 4.0}
    )
    
    print("[TX 502] Additional UPDATE after checkpoint")
    frm.log_write(
        tx_id=502,
        table="mahasiswa",
        pk={"nim": "13520502"},
        old_data={"nim": "13520502", "nama": "Henry", "ipk": 3.7},
        new_data={"nim": "13520502", "nama": "Henry", "ipk": 3.8}
    )
    
    print("[TX 503] Additional INSERT after checkpoint")
    frm.log_write(
        tx_id=503,
        table="dosen",
        pk={"nip": "002"},
        old_data=None,
        new_data={"nip": "002", "nama": "Dr. Eve", "dept": "STI"}
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
    
    print("\n[EXPECTED BEHAVIOR - All Committed Scenario]")
    print("-" * 60)
    print("✓ Checkpoint found with TX [501, 502, 503]")
    print("✓ REDO phase:")
    print("  - T501 UPDATE (committed)")
    print("  - T502 UPDATE (committed)")
    print("  - T503 INSERT (committed)")
    print("✓ After REDO, undo_list should be EMPTY")
    print("  (All transactions committed)")
    print("✓ UNDO phase:")
    print("  - No operations to undo!")
    print("  - No CLR written")
    print("  - No ABORT written")
    
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
    
    assert stats['checkpoint_found'], "❌ Should find checkpoint!"
    assert 501 in stats['checkpoint_transactions'], "❌ T501 should be in checkpoint!"
    assert 502 in stats['checkpoint_transactions'], "❌ T502 should be in checkpoint!"
    assert 503 in stats['checkpoint_transactions'], "❌ T503 should be in checkpoint!"
    assert stats['redo_count'] == 3, f"❌ Should REDO 3 operations, got {stats['redo_count']}"
    assert stats['undo_count'] == 0, f"❌ Should UNDO 0 operations (all committed), got {stats['undo_count']}"
    assert len(stats['undo_list_final']) == 0, f"❌ undo_list should be empty!"
    
    print("✅ All validations passed!")
    print("\n" + "="*60)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("="*60)
    
    # Verify NO CLR written
    print("\n[BONUS] Verifying NO Compensation Logs...")
    from log_parser import LogParser
    parser = LogParser(log_dir)
    
    clr_count = 0
    for entry in parser.iter_backward():
        if entry.action == "clr":
            clr_count += 1
    
    if clr_count == 0:
        print("✅ Correct! No CLR written (all transactions committed)")
    else:
        print(f"⚠️  Found {clr_count} CLR(s) - unexpected for all-committed scenario!")

if __name__ == "__main__":
    main()