from typing import Dict, Any, Union, List
from row_dataclass import BufferedRow, BUFFER_CAPACITY
from log_config import MockChangeReport
from log_writer import LogWriter, ActionType

class MockStorageEngine:
    # Simulasi interaksi I/O disk
    def fetch_block_from_disk(self, table_name: str, pk_value: Any) -> Union[dict, None]:
        print(f"[SM MOCK] -> Membaca data {table_name}:{pk_value} dari disk.")
        return {"id": pk_value, "name": f"Item_{pk_value}", "stock": 100}
    
    def write_block_to_disk(self, row: BufferedRow):
        print(f"[SM MOCK] <- Menulis data DIRTY {row.primary_key_value} ke disk (I/O Selesai).")
        pass

class BufferManager:
    # Mengelola buffer di memori menggunakan kebijakan Least Recently Used (LRU)
    def __init__(self, log_writer: LogWriter, actual_storage_engine: Any = MockStorageEngine, capacity: int = BUFFER_CAPACITY):
        self.capacity = capacity
        self.buffer_data: Dict[tuple, BufferedRow] = {}
        self.lru_order: List[tuple] = []
        self.storage_engine = actual_storage_engine
        self.log_writer = log_writer
    def _get_buffer_key(self, table_name: str, pk_value: Any) -> tuple:
        # Helper untuk mendapatkan kunci unik buffer
        return (table_name, pk_value)
    
    def _update_lru(self, key: tuple):
        # Memindahkan key yang baru diakses ke belakang list (Most Recently Used).
        if key in self.lru_order:
            self.lru_order.remove(key)
        self.lru_order.append(key) # Key baru diakses ditambah di akhir

    ''' Logika Interaksi Buffer '''
    def read_block(self, table_name: str, pk_value: Any) -> BufferedRow:
        key = self._get_buffer_key(table_name, pk_value)
        if key in self.buffer_data:
            self._update_lru(key)
            print(f"[Buffer] Cache hit: {pk_value}. Membaca dari buffer.")
            return self.buffer_data[key]
        print(f"[Buffer] Cache miss: {pk_value}. Mulai baca dari disk...")
        disk_data = self.storage_engine.fetch_block_from_disk(table_name, pk_value)

        if disk_data is None:
            raise FileNotFoundError(f"Data tidak ditemukan di disk untuk PK: {pk_value}")
        new_row = BufferedRow(table_name, pk_value, disk_data, is_dirty=False)
        self._add_to_buffer(new_row, key)
    
    def write_block(self, transaction_id: int, table_name: str, pk_value: Any, new_data: dict) -> MockChangeReport:
        key = self._get_buffer_key(table_name, pk_value)
        if key not in self.buffer_data:
            print("[Buffer] Data untuk write tidak ada di buffer, membaca dulu...")
            self.read_block(table_name, pk_value)
        row = self.buffer_data[key]
        self._update_lru(key) # Update LRU karena data diakses
        
        old_data = row.data.copy() # Nilai lama dicatat untuk Log
        report = MockChangeReport(table_name, old_data, new_data)
        # buat entri log
        log_entry_str = self.log_writer.create_log_entry(
            transaction_id, ActionType.WRITE, report
        )
        # tulis log ke disk dulu
        self.log_writer.write_to_file(log_entry_str)
        row.data = new_data
        row.is_dirty = True
        print(f"[Buffer] Data {pk_value} diubah, ditandai kotor, DAN SUDAH DI-LOG.")
        return report
    
    ''' Manajemen Ukuran Buffer '''
    def _add_to_buffer(self, row: BufferedRow, key:tuple):
        # Menambah baris ke buffer dan mengeluarkan yang lama jika penuh
        if len(self.buffer_data) >= self.capacity:
            self._evict_block() # Panggil logika mengeluarkan (eviction)
        self.buffer_data[key] = row
        self._update_lru(key) # Memasukkan key baru ke urutan LRU
        print(f"[Buffer] Data {row.primary_key_value} berhasil ditambahkan.")

    def _evict_block(self):
        # Logika untuk mengeluarkan blok dari buffer.
        while self.lru_order:
            lru_key = self.lru_order[0]
            row = self.buffer_data[lru_key]
            if not row.is_pinned:
                if row.is_dirty:
                    # Tulis ke disk (WAL) sebelum dikeluarkan
                    self.storage_engine.write_block_to_disk(row)
                    self.lru_order.pop(0) # Hapus dari urutan LRU
                    self.buffer_data.pop(lru_key) # Hapus dari penyimpanan data
                    print(f"[Buffer] Evicted (LRU): {row.primary_key_value}")
                    return
            else: # Pindah ke blok LRU berikutnya
                self.lru_order.pop(0)
                self.lru_order.append(lru_key)
                print(F"[Buffer] Warning: Blok {row.primary_key_value} di-pin, mencoba blok LRU berikutnya.")
        print(f"[Buffer] Warning: buffer penuh dan semua blok di-pin atau tidak dapat dikeluarkan.")
    
    def is_buffer_full(self) -> bool:
        # Mendeteksi kapan buffer sudah penuh
        return len(self.buffer_data) == self.capacity
    
    def is_buffer_almost_full(self) -> bool:
        # Mendeteksi kapan buffer hampir penuh (misalnya 75%)
        return len(self.buffer_data) >= (self.capacity*0.75)
    
    ''' Logika Flush Buffer '''
    def flush_dirty_blocks(self):
        # Menulis semua data 'kotor' di buffer ke disk dan dipanggil saat checkpoint
        dirty_count = 0
        for row in list(self.buffer_data.values()):
            if row.is_dirty:
                self.storage_engine.write_block_to_disk(row)
                row.is_dirty = False
                dirty_count += 1
        
        if dirty_count > 0:
            print(f"[Buffer Manager] Flush selesai: {dirty_count} blok kotor ditulis ke disk.")
        else:
            print(f"[Buffer Manager] Flush: Tidak ada blok kotor yang perlu ditulis.")