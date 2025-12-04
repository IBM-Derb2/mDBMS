"""
Test FailureRecoveryManager - abort_transaction functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from log_config import WalAction

# Import real Storage Engine (jika ada)
try:
    from Storage_Manager.storage_engine import StorageEngine
    from Storage_Manager.utils import DataWrite, DataDeletion, DataRetrieval, Condition
    STORAGE_AVAILABLE = True
    print("[Test] Using REAL Storage Engine")
except ImportError:
    STORAGE_AVAILABLE = False
    print("[Test] Storage Engine not available, using mock")

# Mock BufferManager (Updated untuk Callback Pattern)
class MockBufferManager:
    def __init__(self):
        self.fetch_callback = None
        self.write_callback = None

    def set_load_table_routine(self, callback):
        self.fetch_callback = callback
    
    def set_save_buffer_routine(self, callback):
        self.write_callback = callback

    def is_buffer_almost_full(self):
        return False
    
    def flush_dirty_blocks(self):
        pass

    # Method untuk Recovery/Abort (Logika Undo)
    def write_to_buffer_for_recovery(self, table, pk, data):
        # Dalam kasus Abort, ini dipanggil saat Undo
        print(f"   [Buffer] UNDO WRITE: {table} PK={pk} -> Buffer Updated")
        # Jika menggunakan Real Storage, kita bisa mencoba menulis beneran lewat callback
        if self.write_callback:
            # Sederhana: kita anggap data ini langsung ditulis
            pass
    
    def delete_from_buffer_for_recovery(self, table, pk):
        print(f"   [Buffer] UNDO DELETE: {table} PK={pk} -> Buffer Cleared")


# Setup Storage Engine or Mock
if STORAGE_AVAILABLE:
    storage_eng = StorageEngine()
    
    print("[Test] Using 'student' table with schema:")
    print("  - StudentID (int)")
    print("  - FullName (varchar)")
    print("  - GPA (float)")
    
    # Callback Wrappers untuk Real Storage Engine
    def real_read_callback(table, pk):
        # Konversi format sederhana (table, pk dict) ke DataRetrieval
        conditions = []
        for k, v in pk.items():
            conditions.append(Condition(k, "=", v))
        
        retrieval = DataRetrieval(
            table=table,
            column=["*"],
            conditions=conditions,
            search_type="sequential"
        )
        return storage_eng.read_block(retrieval)

    def real_write_callback(row_obj):
        # Perlu penyesuaian tergantung apa yang dikirim BufferManager
        # Ini hanya mock wrapper jika Buffer mengirim objek Row
        pass

else:
    # MOCK STORAGE (Jika Real Storage tidak ada)
    class MockStorageEngine:
        def write_block(self, data_write):
            print(f"    [MockStorage] write_block: table={getattr(data_write, 'table', 'unknown')}")
            return True
        
        def delete_block(self, data_deletion):
            print(f"    [MockStorage] delete_block: table={getattr(data_deletion, 'table', 'unknown')}")
            return True

        def read_block(self, data_retrieval):
            print(f"    [MockStorage] read_block: table={getattr(data_retrieval, 'table', 'unknown')}")
            return None

    storage_eng = MockStorageEngine()
    
    # Dummy callbacks untuk Mock
    def real_read_callback(table, pk):
        return None
    def real_write_callback(data):
        return True

print("\n" + "="*70)
print("TEST: FailureRecoveryManager - abort_transaction()")
print("="*70)

# Initialize FRM
buffer_mgr = MockBufferManager()

# [UPDATED] Menggunakan Callback Pattern
frm = FailureRecoveryManager(
    buffer_manager=buffer_mgr,
    load_table_callback=real_read_callback if STORAGE_AVAILABLE else storage_eng.read_block,
    save_buffer_callback=real_write_callback if STORAGE_AVAILABLE else storage_eng.write_block,
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
    # Simulasi menulis ke storage langsung (seolah-olah buffer flush)
    data_write = DataWrite(
        table="student",
        column=["StudentID"],
        conditions=[],
        new_value=99999
    )
    storage_eng.write_block(data_write)
    print("  ✓ Alice Test inserted to storage (Simulated)")

# Operation 2: UPDATE student GPA
print("\n[OP 2] UPDATE student GPA (StudentID=99999)")
frm.log_write(
    tx_id=201,
    table="student",
    pk={"StudentID": 99999},
    old_data={"StudentID": 99999, "FullName": "Alice Test", "GPA": 3.5},
    new_data={"StudentID": 99999, "FullName": "Alice Test", "GPA": 3.7}
)

# Operation 3: DELETE another student (StudentID=1)
print("\n[OP 3] DELETE another student (StudentID=1)")
frm.log_write(
    tx_id=201,
    table="student",
    pk={"StudentID": 1},
    old_data={"StudentID": 1, "FullName": "Student_1", "GPA": 3.12},
    new_data=None
)

# Transaction ABORTS!
print("\n" + "="*70)
print("[ABORT] TX 201 is aborting - need to rollback!")
print("="*70)

frm.write_log_entry(201, WalAction.ABORT)

# Ini akan memanggil logic Undo -> BufferManager.write_to_buffer_for_recovery
frm.abort_transaction(201) 

frm.notify_transaction_end(201)

print("\n" + "="*70)
print("TEST COMPLETED!")
print("="*70)
print("\nExpected undo operations (via BufferManager):")
print("1. Undo DELETE: Re-insert Student_1 (StudentID=1)")
print("2. Undo UPDATE: Restore Alice GPA to 3.5")
print("3. Undo INSERT: Delete Alice Test (StudentID=99999)")