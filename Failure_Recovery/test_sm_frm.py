import sys
import os
import shutil
import time

# Setup path agar bisa import modul dari folder lain
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from failure_recovery_manager import FailureRecoveryManager
from buffer_manager import BufferManager
from Storage_Manager.storage_engine import StorageEngine
from log_config import WalAction
from log_writer import LogWriter

# Konfigurasi Direktori Test
TEST_DB_DIR = "test_db_real"
TEST_LOG_DIR = "test_wal_real"

def setup_clean_environment():
    """Membersihkan file sisa test sebelumnya"""
    print(f"\n[Setup] Membersihkan lingkungan test...")
    
    # 1. Bersihkan Data Storage (Folder 'data/test_db_real')
    storage_path = os.path.join("data", TEST_DB_DIR)
    if os.path.exists(storage_path):
        shutil.rmtree(storage_path)
        print(f"  ✓ Hapus folder data lama: {storage_path}")
    
    # 2. Bersihkan Log WAL
    if os.path.exists(TEST_LOG_DIR):
        shutil.rmtree(TEST_LOG_DIR)
        print(f"  ✓ Hapus folder log lama: {TEST_LOG_DIR}")

def create_initial_schema(storage):
    """Membuat skema tabel 'mahasiswa' secara fisik di disk"""
    print(f"\n[Setup] Membuat skema database awal...")
    
    schema_mhs = {
        "table_name": "mahasiswa",
        "columns": [
            {"name": "NIM", "type": "int"},
            {"name": "Nama", "type": "varchar", "length": 50},
            {"name": "IPK", "type": "float"}
        ]
    }
    
    # Write schema & empty data file
    storage.write_schema_file(schema_mhs)
    storage.write_data_file("mahasiswa", [], schema_mhs)
    print(f"  ✓ Tabel 'mahasiswa' berhasil dibuat di disk.")

def main():
    print("="*80)
    print("   REAL INTEGRATION TEST: FRM + BUFFER + REAL STORAGE")
    print("="*80)

    # 1. Persiapan Lingkungan
    setup_clean_environment()
    
    # Inisialisasi Storage Engine Asli
    print("\n[Init] Menginisialisasi komponen...")
    real_storage = StorageEngine(data_dir=TEST_DB_DIR)
    create_initial_schema(real_storage)
    
    log_writer = LogWriter(TEST_LOG_DIR)
    
    # Buffer Manager (Pastikan sudah versi Table-Level yang ada self.tables)
    buffer_mgr = BufferManager(log_writer)
    
    # FRM dengan Callback ke Real Storage
    frm = FailureRecoveryManager(
        buffer_manager=buffer_mgr,
        # Callback ini menghubungkan Buffer ke fungsi I/O asli StorageEngine
        load_table_callback=real_storage.read_disk_to_buffer,
        save_buffer_callback=real_storage.save_buffer_to_disk,
        log_directory=TEST_LOG_DIR
    )
    
    # 2. Skenario Transaksi
    print("\n" + "-"*50)
    print("PHASE 1: TRANSAKSI & CHECKPOINT")
    print("-"*50)
    
    # --- TX 101: Insert Data & Commit ---
    print("\n> TX 101: Insert 'Andi' (NIM 101)")
    frm.notify_transaction_start(101)
    frm.write_log_entry(101, WalAction.START)
    
    # Menulis ke Buffer (Data masuk memori, status Dirty)
    # Note: Di real app, data dikirim dalam bentuk dict yang sesuai skema
    buffer_mgr.write_block(
        transaction_id=101,
        table_name="mahasiswa",
        pk_value={"NIM": 101},
        new_data={"NIM": 101, "Nama": "Andi Saputra", "IPK": 3.5}
    )
    
    frm.write_log_entry(101, WalAction.COMMIT)
    frm.notify_transaction_end(101)
    print("  ✓ TX 101 Committed (Data masih di Buffer RAM)")
    
    # --- CHECKPOINT (Flush ke Disk Asli) ---
    print("\n> Memicu CHECKPOINT...")
    # Ini akan memanggil buffer_mgr.flush_dirty_blocks()
    # Lalu memanggil real_storage.save_buffer_to_disk()
    frm.save_checkpoint([]) 
    print("  ✓ Checkpoint selesai. Data harusnya sudah ada di file .dat")
    
    # --- TX 102: Insert Data & CRASH (Belum Commit) ---
    print("\n> TX 102: Insert 'Budi' (NIM 102) -> CRASH SCENARIO")
    frm.notify_transaction_start(102)
    frm.write_log_entry(102, WalAction.START)

    buffer_mgr.write_block(
        transaction_id=102,
        table_name="mahasiswa",
        pk_value={"NIM": 102},
        new_data={"NIM": 102, "Nama": "Budi Santoso", "IPK": 2.8}
    )
    print("  ✓ TX 102 Inserted to Buffer (Dirty)")
    
    # --- TX 103: Insert Data & Commit (Setelah Checkpoint) ---
    print("\n> TX 103: Insert 'Citra' (NIM 103) -> Committed")
    frm.notify_transaction_start(103)
    frm.write_log_entry(103, WalAction.START)

    buffer_mgr.write_block(
        transaction_id=103,
        table_name="mahasiswa",
        pk_value={"NIM": 103},
        new_data={"NIM": 103, "Nama": "Citra Lestari", "IPK": 3.9}
    )
    
    frm.write_log_entry(103, WalAction.COMMIT)
    frm.notify_transaction_end(103)
    print("  ✓ TX 103 Committed (Data di Buffer, belum Flush ke Disk)")
    
    # 3. SIMULASI CRASH
    print("\n" + "!"*50)
    print("           💥 SYSTEM CRASH (MATI LISTRIK) 💥")
    print("!"*50)
    
    # Kita hancurkan objek memori untuk mensimulasikan hilangnya data RAM
    del buffer_mgr
    del frm
    del real_storage
    
    # 4. RECOVERY
    print("\n" + "-"*50)
    print("PHASE 2: SYSTEM RESTART & RECOVERY")
    print("-"*50)
    
    # Init ulang komponen (seperti restart server)
    print("[Recovery] Menyalakan ulang sistem...")
    storage_new = StorageEngine(data_dir=TEST_DB_DIR) # Baca dari folder yang sama
    log_new = LogWriter(TEST_LOG_DIR)
    buffer_new = BufferManager(log_new)
    
    frm_new = FailureRecoveryManager(
        buffer_manager=buffer_new,
        load_table_callback=storage_new.read_disk_to_buffer,
        save_buffer_callback=storage_new.save_buffer_to_disk,
        log_directory=TEST_LOG_DIR
    )
    
    # Jalankan Recovery
    print("[Recovery] Memulai proses recovery...")
    frm_new.recover()
    print("[Recovery] Selesai.")
    
    # 5. VERIFIKASI DATA (BACA DARI FILE FISIK)
    print("\n" + "-"*50)
    print("PHASE 3: VERIFIKASI DATA FINAL")
    print("-"*50)
    
    # Kita baca langsung file fisik menggunakan StorageEngine
    from Storage_Manager.utils import DataRetrieval
    
    print("Membaca data aktual dari disk...")
    # Select * from mahasiswa
    retrieval = DataRetrieval(table="mahasiswa", column=[], conditions=[]) 
    result = storage_new.read_block(retrieval)
    
    final_data = {}
    print("\nIsi Tabel 'Mahasiswa' di Disk:")
    for row in result.data:
        nim = row['NIM']
        nama = row['Nama']
        final_data[nim] = nama
        print(f"  - NIM: {nim} | Nama: {nama} | IPK: {row['IPK']}")
        
    # --- ASSERTIONS ---
    print("\n[Validasi Hasil]")
    try:
        # 1. Cek Data Checkpoint (Andi)
        if 101 in final_data:
            print("  ✅ [PASS] Andi (TX 101) ada (Saved by Checkpoint).")
        else:
            raise AssertionError("❌ [FAIL] Andi hilang! Checkpoint gagal menulis ke disk.")

        # 2. Cek Data Redo (Citra)
        if 103 in final_data:
            print("  ✅ [PASS] Citra (TX 103) ada (Restored by REDO).")
        else:
            raise AssertionError("❌ [FAIL] Citra hilang! Recovery REDO gagal.")

        # 3. Cek Data Undo (Budi)
        if 102 not in final_data:
            print("  ✅ [PASS] Budi (TX 102) tidak ada (Rolled back by UNDO).")
        else:
            raise AssertionError("❌ [FAIL] Budi masih ada! Recovery UNDO gagal/Data bocor.")

        print("\n🎉 INTEGRATION TEST SUCCESS: Semua komponen (Storage, Buffer, FRM) bekerja harmonis!")
        
    except AssertionError as e:
        print(f"\n{e}")
        print("Test Gagal.")

if __name__ == "__main__":
    main()