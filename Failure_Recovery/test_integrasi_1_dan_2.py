import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Impor dari Orang 1 (Anda)
from log_writer import LogWriter
from log_config import ActionType

# Impor dari Orang 2
from buffer_manager import BufferManager, MockStorageEngine, BUFFER_CAPACITY
from row_dataclass import BUFFER_CAPACITY # (Mungkin duplikat, pastikan impornya benar)

print("--- [SIMULASI INTEGRASI 1 + 2] ---")

# Buat folder log & file log Anda (Orang 1)
lw = LogWriter(log_directory="test_integrasi_logs")

# Buat mock storage engine
sm_mock = MockStorageEngine()

# Buat Buffer Manager (Orang 2) dan "berikan" LogWriter Anda
bm = BufferManager(
    actual_storage_engine=sm_mock, 
    log_writer=lw, 
    capacity=BUFFER_CAPACITY
)

# --- 2. SIMULASI TRANSAKSI ---
TX_ID_101 = 101
print(f"\n[A] Transaksi {TX_ID_101} dimulai...")
# Kita catat log START secara manual (ini nanti tugas Query Processor)
log_start = lw.create_log_entry(TX_ID_101, ActionType.START)
lw.write_to_file(log_start)

# Transaksi 101 ingin MENGUBAH blok 1
print(f"\n[B] Transaksi {TX_ID_101} melakukan WRITE Blok 1")
new_data_1 = {"id": 1, "name": "Produk_A_Revisi", "stock": 50}

# Panggil `write_block` yang sudah terintegrasi
# Ini akan:
# 1. Menulis log WRITE (via LogWriter)
# 2. Mengubah data di buffer dan menandainya 'dirty'
bm.write_block(TX_ID_101, "products", 1, new_data_1)
# Output console akan menunjukkan:
# [Buffer] Cache miss: 1...
# [SM MOCK] -> Membaca data...
# [Buffer] Data 1 berhasil ditambahkan.
# [LogWriter] File log baru telah dibuat... (Jika baru pertama kali)
# [Buffer] Data 1 diubah, ditandai kotor, DAN SUDAH DI-LOG.

print(f"\n[C] Transaksi {TX_ID_101} melakukan COMMIT")
# Kita catat log COMMIT
log_commit = lw.create_log_entry(TX_ID_101, ActionType.COMMIT)
lw.write_to_file(log_commit)

print("\n[D] MENGISI BUFFER (Sama seperti tes Orang 2)")
bm.read_block("products", 2)
bm.read_block("products", 3)
bm.read_block("products", 4)
print(f"Urutan LRU: {bm.lru_order}")

print("\n[E] MENGAKSES BLOK 5 (TRIGGER EVICTION)")
# Blok 1 (products:1) adalah LRU dan statusnya DIRTY
# BufferManager akan memanggil _evict_block()
# _evict_block() akan memanggil storage_engine.write_block_to_disk(row_1)
# Ini sekarang AMAN, karena log untuk Blok 1 sudah ditulis di langkah [B]
bm.read_block("products", 5) 

print(f"\nUrutan LRU setelah eviction: {bm.lru_order}")
print("\n--- SIMULASI SELESAI ---")
print(f"Silakan cek file log di folder: '{lw.log_directory}'")