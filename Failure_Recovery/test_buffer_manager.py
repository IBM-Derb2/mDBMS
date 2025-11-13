import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from buffer_manager import BufferManager, MockStorageEngine, BUFFER_CAPACITY
from log_writer import LogWriter
from log_config import ActionType
lw_untuk_tes_buffer = LogWriter(log_directory="test_logs_buffer_only")
TEST_TX_ID = 999 

PK_1 = {"id": 1}
PK_2 = {"id": 2}
PK_3 = {"id": 3}
PK_4 = {"id": 4}
PK_5 = {"id": 5}
# Inisialisasi Buffer Manager dengan Mock Storage Engine
sm_mock = MockStorageEngine()
bm = BufferManager(
    log_writer=lw_untuk_tes_buffer, # Ini sekarang wajib ada
    actual_storage_engine=sm_mock, 
    capacity=BUFFER_CAPACITY
) 

print(f"Kapasitas Buffer: {BUFFER_CAPACITY} blok.")

print("\n[A] MENGAKSES BLOK 1 (MISS)")
block_1 = bm.read_block("products", PK_1)
# Key LRU yang tersimpan sekarang adalah tuple hashable dari PK_1

print("\n[B] MENGAKSES BLOK 1 LAGI (HIT)")
bm.read_block("products", PK_1) 

print("\n[C] MENGUBAH BLOK 1 (WRITE)")
new_data_1 = {"id": 1, "name": "Produk_A_Revisi", "stock": 50}
report_1 = bm.write_block(TEST_TX_ID, "products", PK_1, new_data_1)
print(f"Blok 1 Dirty?: {bm.buffer_data[bm._get_buffer_key('products', PK_1)].is_dirty}")

print("\n[D] MENGISI BUFFER HINGGA PENUH")
bm.read_block("products", PK_2) 
bm.read_block("products", PK_3) 
bm.read_block("products", PK_4) 
print(f"Buffer Penuh?: {bm.is_buffer_full()}")
print(f"Urutan LRU saat ini: {bm.lru_order}")

print("\n[E] MENGAKSES BLOK 5 (TRIGGER EVICTION)")
# Blok 1 (PK_1) adalah yang LRU dan DIRTY. Akan di-FLUSH dan di-EVICT.
bm.read_block("products", PK_5) 
print(f"Urutan LRU setelah eviction: {bm.lru_order}")
print(f"Blok 1 masih ada di buffer?: {bm._get_buffer_key('products', PK_1) in bm.buffer_data}")

print("\n[F] MEMANGGIL FLUSH DIRTY BLOCKS (CHECKPOINT)")
bm.flush_dirty_blocks()
pk_key_5 = bm._get_buffer_key('products', PK_5)
# Cek Blok 5 (yang tidak pernah di-write/dirty)
print(f"Blok 5 Dirty setelah flush?: {bm.buffer_data[pk_key_5].is_dirty if pk_key_5 in bm.buffer_data else 'N/A'}")

print("\n--- SIMULASI SELESAI ---")