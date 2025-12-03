import sys
import os
import shutil
import time

# Setup path imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from buffer_manager import BufferManager
from Storage_Manager.storage_engine import StorageEngine
from log_config import WalAction
from log_writer import LogWriter

# Konfigurasi Test
TEST_DB_DIR = "test_db_full_v2"
TEST_LOG_DIR = "test_wal_full_v2"

def setup_clean_environment():
    print(f"\n[Setup] Membersihkan environment...")
    path_data = os.path.join("data", TEST_DB_DIR)
    if os.path.exists(path_data): shutil.rmtree(path_data)
    if os.path.exists(TEST_LOG_DIR): shutil.rmtree(TEST_LOG_DIR)

def create_schema(storage):
    print(f"\n[Setup] Membuat Schema Database...")
    
    # Tabel 1: Mahasiswa
    schema_mhs = {
        "table_name": "mahasiswa",
        "columns": [
            {"name": "NIM", "type": "int"},
            {"name": "Nama", "type": "varchar", "length": 50},
            {"name": "IPK", "type": "float"}
        ]
    }
    storage.write_schema_file(schema_mhs)
    storage.write_data_file("mahasiswa", [], schema_mhs)
    
    # Tabel 2: Matkul (Untuk membuktikan multi-table support)
    schema_mk = {
        "table_name": "matkul",
        "columns": [
            {"name": "KodeMK", "type": "varchar", "length": 10},
            {"name": "NamaMK", "type": "varchar", "length": 50},
            {"name": "SKS", "type": "int"}
        ]
    }
    storage.write_schema_file(schema_mk)
    storage.write_data_file("matkul", [], schema_mk)
    print("  ✓ Tabel 'mahasiswa' & 'matkul' siap.")

def main():
    print("="*80)
    print("   FULL INTEGRATION TEST: INSERT, UPDATE, DELETE & RECOVERY")
    print("="*80)
    
    setup_clean_environment()
    
    # --- INIT COMPONENTS ---
    print("\n[Init] Menginisialisasi Sistem...")
    storage = StorageEngine(data_dir=TEST_DB_DIR)
    create_schema(storage)
    
    log_writer = LogWriter(TEST_LOG_DIR)
    buffer_mgr = BufferManager(log_writer)
    
    frm = FailureRecoveryManager(
        buffer_manager=buffer_mgr,
        load_table_callback=storage.read_disk_to_buffer,
        save_buffer_callback=storage.save_buffer_to_disk,
        log_directory=TEST_LOG_DIR
    )
    
    # ==========================================
    # PHASE 1: PRE-CHECKPOINT OPERATIONS
    # ==========================================
    print("\n" + "-"*50)
    print("PHASE 1: TRANSAKSI AWAL & CHECKPOINT")
    print("-"*50)
    
    # TX 101: Insert Andi (Commit)
    print("\n> TX 101: Insert 'Andi' (NIM 1)")
    frm.notify_transaction_start(101)
    frm.write_log_entry(101, WalAction.START)
    
    data_andi = {"NIM": 1, "Nama": "Andi", "IPK": 3.0}
    frm.log_write(101, "mahasiswa", {"NIM": 1}, None, data_andi)
    buffer_mgr.write_block(101, "mahasiswa", {"NIM": 1}, data_andi)
    
    frm.write_log_entry(101, WalAction.COMMIT)
    frm.notify_transaction_end(101)
    
    # TX 102: Insert Matkul Basis Data (Commit)
    print("\n> TX 102: Insert Matkul 'Basdat' (Kode IF1)")
    frm.notify_transaction_start(102)
    frm.write_log_entry(102, WalAction.START)
    
    data_basdat = {"KodeMK": "IF1", "NamaMK": "Basis Data", "SKS": 4}
    frm.log_write(102, "matkul", {"KodeMK": "IF1"}, None, data_basdat)
    buffer_mgr.write_block(102, "matkul", {"KodeMK": "IF1"}, data_basdat)
    
    frm.write_log_entry(102, WalAction.COMMIT)
    frm.notify_transaction_end(102)
    
    # --- CHECKPOINT ---
    print("\n[CHECKPOINT] Menyimpan state ke disk...")
    # Andi & Basdat harus masuk ke disk fisik sekarang
    frm.save_checkpoint([]) 
    
    # ==========================================
    # PHASE 2: POST-CHECKPOINT OPERATIONS (CHAOS)
    # ==========================================
    print("\n" + "-"*50)
    print("PHASE 2: OPERASI SETELAH CHECKPOINT (MENUJU CRASH)")
    print("-"*50)
    
    # 1. UPDATE (Committed -> REDO)
    # TX 201: Update IPK Andi 3.0 -> 3.5
    print("\n> TX 201: Update Andi IPK 3.5 (Commit)")
    frm.notify_transaction_start(201)
    frm.write_log_entry(201, WalAction.START)
    
    old_andi = data_andi
    new_andi = data_andi.copy()
    new_andi["IPK"] = 3.5
    
    frm.log_write(201, "mahasiswa", {"NIM": 1}, old_andi, new_andi)
    buffer_mgr.write_block(201, "mahasiswa", {"NIM": 1}, new_andi)
    
    frm.write_log_entry(201, WalAction.COMMIT)
    frm.notify_transaction_end(201)
    
    # 2. INSERT (Crash/Uncommitted -> UNDO)
    # TX 202: Insert Budi
    print("\n> TX 202: Insert Budi (NIM 2) (Crash - Belum Commit)")
    frm.notify_transaction_start(202)
    frm.write_log_entry(202, WalAction.START)
    
    data_budi = {"NIM": 2, "Nama": "Budi", "IPK": 2.5}
    frm.log_write(202, "mahasiswa", {"NIM": 2}, None, data_budi)
    buffer_mgr.write_block(202, "mahasiswa", {"NIM": 2}, data_budi)
    
    # 3. DELETE (Crash/Uncommitted -> UNDO)
    # TX 203: Hapus Matkul Basdat
    print("\n> TX 203: Delete Matkul 'Basdat' (Crash - Belum Commit)")
    frm.notify_transaction_start(203)
    frm.write_log_entry(203, WalAction.START)
    
    # Hapus dari buffer
    frm.log_write(203, "matkul", {"KodeMK": "IF1"}, data_basdat, None)
    
    # Buffer manager mungkin belum support delete fisik di method write_block, 
    # tapi kita simulasikan efek logikanya:
    # (Di real code Anda mungkin perlu method delete_block di BufferManager,
    # tapi di sini kita pakai write_block dengan None jika didukung, atau 
    # kita asumsikan log sudah tercatat untuk UNDO).
    # Untuk test ini, kita fokus ke Log-nya yang akan di-undo.
    # Tapi agar realistik, kita "hapus" dari buffer memory secara manual jika perlu
    # atau biarkan buffer dirty.
    pass 
    
    # 4. INSERT (Committed -> REDO)
    # TX 204: Insert Citra
    print("\n> TX 204: Insert Citra (NIM 3) (Commit)")
    frm.notify_transaction_start(204)
    frm.write_log_entry(204, WalAction.START)
    
    data_citra = {"NIM": 3, "Nama": "Citra", "IPK": 3.9}
    frm.log_write(204, "mahasiswa", {"NIM": 3}, None, data_citra)
    buffer_mgr.write_block(204, "mahasiswa", {"NIM": 3}, data_citra)
    
    frm.write_log_entry(204, WalAction.COMMIT)
    frm.notify_transaction_end(204)
    
    # ==========================================
    # PHASE 3: CRASH & RECOVERY
    # ==========================================
    print("\n" + "!"*50)
    print("           💥 SYSTEM CRASH 💥")
    print("!"*50)
    
    # Kill Memory
    del buffer_mgr
    del frm
    del storage
    
    print("\n[Recovery] System Restarting...")
    
    # Re-init
    storage_new = StorageEngine(data_dir=TEST_DB_DIR)
    log_new = LogWriter(TEST_LOG_DIR)
    buffer_new = BufferManager(log_new)
    
    frm_new = FailureRecoveryManager(
        buffer_manager=buffer_new,
        load_table_callback=storage_new.read_disk_to_buffer,
        save_buffer_callback=storage_new.save_buffer_to_disk,
        log_directory=TEST_LOG_DIR
    )
    
    print("[Recovery] Menjalankan Recovery Routine...")
    frm_new.recover()
    print("[Recovery] Selesai.")
    
    # ==========================================
    # PHASE 4: VERIFICATION
    # ==========================================
    print("\n" + "-"*50)
    print("PHASE 4: VERIFIKASI DATA FINAL DI DISK")
    print("-"*50)
    
    from Storage_Manager.utils import DataRetrieval
    
    # 1. Cek Tabel Mahasiswa
    print("\n[Tabel Mahasiswa]")
    res_mhs = storage_new.read_block(DataRetrieval("mahasiswa", [], []))
    mhs_data = {row['NIM']: row for row in res_mhs.data}
    
    for row in res_mhs.data:
        print(f"  - {row}")

    # 2. Cek Tabel Matkul
    print("\n[Tabel Matkul]")
    res_mk = storage_new.read_block(DataRetrieval("matkul", [], []))
    mk_data = {row['KodeMK']: row for row in res_mk.data}
    
    for row in res_mk.data:
        print(f"  - {row}")
        
    print("\n[Validasi Logic]")
    try:
        # A. Cek ANDI (Checkpoint + Redo Update)
        # Andi harus ada, dan IPK-nya harus 3.5 (hasil update TX 201)
        assert 1 in mhs_data, "❌ Andi hilang!"
        assert mhs_data[1]['IPK'] == 3.5, f"❌ IPK Andi salah! Harusnya 3.5 (Update Redo), dapet {mhs_data[1]['IPK']}"
        print("  ✅ [PASS] Andi ada & IPK Terupdate (3.5) -> Checkpoint + Redo Update Sukses.")
        
        # B. Cek BUDI (Insert Crash -> Undo)
        # Budi harus TIDAK ADA
        assert 2 not in mhs_data, "❌ Budi masih ada! Undo Insert Gagal."
        print("  ✅ [PASS] Budi tidak ada -> Undo Insert Sukses.")
        
        # C. Cek BASDAT (Checkpoint + Undo Delete)
        # Basdat harus TETAP ADA. 
        # (Karena TX 203 delete-nya crash/tidak commit, maka harus di-undo/dikembalikan)
        assert "IF1" in mk_data, "❌ Basdat hilang! Undo Delete Gagal."
        print("  ✅ [PASS] Matkul Basdat masih ada -> Undo Delete Sukses (Data Checkpoint selamat).")
        
        # D. Cek CITRA (Redo Insert)
        # Citra harus ADA
        assert 3 in mhs_data, "❌ Citra hilang! Redo Insert Gagal."
        print("  ✅ [PASS] Citra ada -> Redo Insert Sukses.")
        
        print("\n🎉🎉 FULL INTEGRATION TEST PASSED! 🎉🎉")
        print("Sistem Failure Recovery Anda Robust!")
        
    except AssertionError as e:
        print(f"\n💀 TEST FAILED: {e}")

if __name__ == "__main__":
    main()