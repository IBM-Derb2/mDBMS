import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from buffer_manager import BufferManager, MockStorageEngine, BUFFER_CAPACITY
from log_writer import LogWriter, ActionType
lw_untuk_tes_buffer = LogWriter(log_directory="test_logs_buffer_only")
TEST_TX_ID = 999 

# Inisialisasi Buffer Manager dengan Mock Storage Engine
sm_mock = MockStorageEngine()
bm = BufferManager(
    log_writer=lw_untuk_tes_buffer, # Ini sekarang wajib ada
    actual_storage_engine=sm_mock, 
    capacity=BUFFER_CAPACITY
) 

print(f"Kapasitas Buffer: {BUFFER_CAPACITY} blok.")

print("\n[A] MENGAKSES BLOK 1 (MISS)")
block_1 = bm.read_block("products", 1)
# Urutan LRU: [1]

print("\n[B] MENGAKSES BLOK 1 LAGI (HIT)")
bm.read_block("products", 1) # Harusnya Cache Hit
# Urutan LRU: [1] (dipindahkan ke belakang, tapi karena cuma 1, tetap di belakang)

print("\n[C] MENGUBAH BLOK 1 (WRITE)")
new_data_1 = {"id": 1, "name": "Produk_A_Revisi", "stock": 50}
report_1 = bm.write_block(TEST_TX_ID, "products", 1, new_data_1)
print(f"Blok 1 Dirty?: {bm.buffer_data[bm._get_buffer_key('products', 1)].is_dirty}")

print("\n[D] MENGISI BUFFER HINGGA PENUH")
bm.read_block("products", 2) # Urutan LRU: [1, 2]
bm.read_block("products", 3) # Urutan LRU: [1, 2, 3]
bm.read_block("products", 4) # Urutan LRU: [1, 2, 3, 4]
print(f"Buffer Penuh?: {bm.is_buffer_full()}")
print(f"Urutan LRU saat ini: {bm.lru_order}")

print("\n[E] MENGAKSES BLOK 5 (TRIGGER EVICTION)")
# Blok 1 adalah yang paling lama diakses, dan DIRTY.
# Output harusnya: Blok 1 di-FLUSH, lalu di-EVICT.
bm.read_block("products", 5) 
# Urutan LRU Baru: [2, 3, 4, 5]
print(f"Urutan LRU setelah eviction: {bm.lru_order}")
print(f"Blok 1 masih ada di buffer?: {('products', 1) in bm.buffer_data}")

print("\n[F] MEMANGGIL FLUSH DIRTY BLOCKS (CHECKPOINT)")
bm.flush_dirty_blocks()
print(f"Blok 5 Dirty setelah flush?: {bm.buffer_data[bm._get_buffer_key('products', 5)].is_dirty if bm._get_buffer_key('products', 5) in bm.buffer_data else 'N/A'}")

print("\n--- SIMULASI SELESAI ---")