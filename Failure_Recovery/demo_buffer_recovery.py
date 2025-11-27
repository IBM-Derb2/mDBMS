"""
Demo: Buffer-Based Recovery System
Menunjukkan bagaimana recovery write ke buffer, bukan langsung ke disk
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction
from buffer_manager import BufferManager, MockStorageEngine
from log_writer import LogWriter

print("="*70)
print("DEMO: Buffer-Based Recovery System")
print("="*70)

log_dir = "demo_buffer_recovery_logs"
os.makedirs(log_dir, exist_ok=True)

# Clean up old logs
for f in os.listdir(log_dir):
    os.remove(os.path.join(log_dir, f))

# Initialize components
print("\n[SETUP] Initializing components...")
log_writer = LogWriter(log_directory=log_dir)
storage_engine = MockStorageEngine()
buffer_mgr = BufferManager(
    log_writer=log_writer,
    actual_storage_engine=storage_engine,
    capacity=4  # Small capacity to show buffer behavior
)

frm = FailureRecoveryManager(
    buffer_manager=buffer_mgr,
    storage_engine=storage_engine,
    log_directory=log_dir
)

print("✓ Components initialized")
print(f"  - Buffer capacity: {buffer_mgr.capacity} blocks")
print(f"  - Log directory: {log_dir}")

# ========== PHASE 1: Normal Operations ==========
print("\n" + "="*70)
print("PHASE 1: Normal Operations (Before Crash)")
print("="*70)

# TX 101: INSERT new student
print("\n[TX 101] Starting transaction...")
frm.notify_transaction_start(101)
frm.write_log_entry(101, WalAction.START)

print("[TX 101] INSERT operation on student")
frm.log_write(
    tx_id=101,
    table="student",
    pk={"StudentID": 1001},
    old_data=None,
    new_data={"StudentID": 1001, "FullName": "Alice Buffer", "GPA": 3.8}
)

# Simulate buffer write
buffer_mgr.write_to_buffer_for_recovery(
    table_name="student",
    pk_value={"StudentID": 1001},
    new_data={"StudentID": 1001, "FullName": "Alice Buffer", "GPA": 3.8}
)

print(f"\n📊 Buffer Status: {len(buffer_mgr.buffer_data)}/{buffer_mgr.capacity} blocks")
print(f"   Dirty blocks: {sum(1 for row in buffer_mgr.buffer_data.values() if row.is_dirty)}")

# TX 102: UPDATE student
print("\n[TX 102] Starting transaction...")
frm.notify_transaction_start(102)
frm.write_log_entry(102, WalAction.START)

print("[TX 102] UPDATE operation on student")
frm.log_write(
    tx_id=102,
    table="student",
    pk={"StudentID": 1001},
    old_data={"StudentID": 1001, "FullName": "Alice Buffer", "GPA": 3.8},
    new_data={"StudentID": 1001, "FullName": "Alice Buffer", "GPA": 4.0}
)

buffer_mgr.write_to_buffer_for_recovery(
    table_name="student",
    pk_value={"StudentID": 1001},
    new_data={"StudentID": 1001, "FullName": "Alice Buffer", "GPA": 4.0}
)

# CHECKPOINT
print("\n" + "="*70)
print("CHECKPOINT: Saving state...")
print("="*70)
ongoing_txs = list(frm.active_transactions)
frm.save_checkpoint(ongoing_txs)
print(f"Checkpoint saved with ongoing transactions: {ongoing_txs}")
print(f"✓ Buffer flushed to disk during checkpoint")
print(f"📊 Buffer Status after flush: {len(buffer_mgr.buffer_data)}/{buffer_mgr.capacity} blocks")

# After checkpoint - more operations
print("\n[TX 102] Additional UPDATE after checkpoint")
frm.log_write(
    tx_id=102,
    table="student",
    pk={"StudentID": 1001},
    old_data={"StudentID": 1001, "FullName": "Alice Buffer", "GPA": 4.0},
    new_data={"StudentID": 1001, "FullName": "Alice Buffer", "GPA": 3.9}
)

# TX 101: COMMIT
print("\n[TX 101] Committing...")
frm.write_log_entry(101, WalAction.COMMIT)
frm.notify_transaction_end(101)

# TX 102: Still ongoing - will need UNDO!
print("\n[TX 102] Still ongoing (will crash!)...")

print("\n" + "="*70)
print("💥 SYSTEM CRASH! 💥")
print("="*70)
print("System restarting...\n")

# ========== PHASE 2: Recovery ==========
print("="*70)
print("PHASE 2: Buffer-Based Recovery")
print("="*70)

# Create new FRM instance (simulate restart)
print("\n[Recovery] Creating new FRM instance (system restart)...")
log_writer_recovery = LogWriter(log_directory=log_dir)
buffer_mgr_recovery = BufferManager(
    log_writer=log_writer_recovery,
    actual_storage_engine=storage_engine,
    capacity=4
)

frm_recovery = FailureRecoveryManager(
    buffer_manager=buffer_mgr_recovery,
    storage_engine=storage_engine,
    log_directory=log_dir
)

print(f"📊 Buffer Status before recovery: {len(buffer_mgr_recovery.buffer_data)}/{buffer_mgr_recovery.capacity} blocks")

# Run recovery
print("\n[Recovery] Starting recovery process...")
print("  → Step 1: Expand buffer for recovery")
print("  → Step 2: REDO phase (write to buffer)")
print("  → Step 3: UNDO phase (write to buffer)")  
print("  → Step 4: Flush buffer to disk\n")

stats = frm_recovery.recover()

# ========== PHASE 3: Verification ==========
print("\n" + "="*70)
print("PHASE 3: Verification")
print("="*70)

print("\n[KEY DIFFERENCE: Buffer-Based vs Direct-to-Disk]")
print("-" * 70)
print("❌ OLD WAY (Direct to Disk):")
print("   Recovery → storage_engine.write_block() → DISK")
print("   Problem: Bypass buffer, no transaction isolation")
print()
print("✅ NEW WAY (Buffer-Based):")
print("   Recovery → buffer_manager.write_to_buffer_for_recovery() → BUFFER")
print("   Then: buffer_manager.flush_dirty_blocks() → DISK")
print("   Benefits: Consistent architecture, better performance, idempotent")

print("\n[RECOVERY STATISTICS]")
print("-" * 70)
print(f"Checkpoint found: {stats['checkpoint_found']}")
print(f"Checkpoint transactions: {stats['checkpoint_transactions']}")
print(f"REDO operations: {stats['redo_count']}")
print(f"UNDO operations: {stats['undo_count']}")

print("\n[BUFFER METRICS]")
print("-" * 70)
print(f"Buffer capacity during recovery: {buffer_mgr_recovery.capacity} blocks")
print(f"  (Expanded from 4 to {buffer_mgr_recovery.capacity} to avoid evictions)")
print(f"Final buffer state: {len(buffer_mgr_recovery.buffer_data)} blocks")
print(f"  (Should be empty after flush)")

print("\n" + "="*70)
print("✅ DEMO COMPLETED!")
print("="*70)
print("\n💡 Key Takeaways:")
print("  1. Recovery operations write to BUFFER, not direct to disk")
print("  2. Buffer expands during recovery to avoid evictions")
print("  3. All recovered data is flushed at END of recovery")
print("  4. This ensures consistency and idempotent recovery")
print(f"\n📂 Check WAL logs in: {log_dir}/")