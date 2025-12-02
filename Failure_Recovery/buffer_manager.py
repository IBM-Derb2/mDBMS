from typing import Dict, Any, Union, List
from row_dataclass import BufferedRow, BUFFER_CAPACITY
from log_config import MockChangeReport
from log_writer import LogWriter, ActionType


class TableWrapper:
    def __init__(self, name, data):
        self.name = name
        self.data = data

class BufferManager:
    # Mengelola buffer di memori menggunakan kebijakan Least Recently Used (LRU)
    def __init__(self, log_writer: LogWriter, capacity: int = BUFFER_CAPACITY):
        self.capacity = capacity
        self.buffer_data: Dict[tuple, BufferedRow] = {}
        self.lru_order: List[tuple] = []
        self.log_writer = log_writer
        
        # Callback functions - to be set by Storage Manager
        self.load_table_callback = None
        self.save_buffer_callback = None
    
    def set_load_table_routine(self, callback):
        """Register callback for fetching blocks from disk (called by Storage Manager)"""
        self.load_table_callback = callback
    
    def set_save_buffer_routine(self, callback):
        """Register callback for writing blocks to disk (called by Storage Manager)"""
        self.save_buffer_callback = callback
    
    def _get_buffer_key(self, table_name: str, pk_value: Dict[str, Any]) -> tuple:
        # Helper untuk mendapatkan kunci unik buffer
        return (table_name, tuple(sorted(pk_value.items())))
    
    def _update_lru(self, key: tuple):
        # Memindahkan key yang baru diakses ke belakang list (Most Recently Used).
        if key in self.lru_order:
            self.lru_order.remove(key)
        self.lru_order.append(key) # Key baru diakses ditambah di akhir

    ''' Logika Interaksi Buffer '''
    def read_block(self, table_name: str, pk_value: Dict[str, Any]) -> BufferedRow:
        key = self._get_buffer_key(table_name, pk_value)
        pk_str = str(pk_value)

        if key in self.buffer_data:
            self._update_lru(key)
            print(f"[Buffer] Cache hit: {pk_str}. Membaca dari buffer.")
            return self.buffer_data[key]
        print(f"[Buffer] Cache miss: {pk_str}. Memuat tabel '{table_name}' dari disk...")
        table_obj = self.load_table_callback(table_name) # type: ignore

        if table_obj is None or not hasattr(table_obj, 'data'):
            raise FileNotFoundError(f"Tabel {table_name} tidak ditemukan atau kosong.")
        found_row = None
        for row_data in table_obj.data:
            is_match = True
            for k, v in pk_value.items():
                if row_data.get(k) != v:
                    is_match = False
                    break
            if is_match:
                new_buffered_row = BufferedRow(table_name, pk_value, row_data, is_dirty=False)
                self._add_to_buffer(new_buffered_row, key)
                found_row = new_buffered_row
        if found_row:
            return found_row
        else:
            raise FileNotFoundError(f"Data tidak ditemukan di tabel {table_name} untuk PK: {pk_str}")

    def write_block(self, transaction_id: int, table_name: str, pk_value: Dict[str, Any], new_data: dict) -> MockChangeReport:
        key = self._get_buffer_key(table_name, pk_value)
        if key not in self.buffer_data:
            print("[Buffer] Data untuk write tidak ada di buffer, membaca dulu...")
            self.read_block(table_name, pk_value)
        row = self.buffer_data[key]
        self._update_lru(key) # Update LRU karena data diakses
        
        old_data = row.data.copy() # Nilai lama dicatat untuk Log
        report = MockChangeReport(table_name, pk_value, old_data, new_data)
        # buat entri log
        log_entry_str = self.log_writer.create_log_entry(
            transaction_id, ActionType.WRITE, report
        )
        # tulis log ke disk dulu
        self.log_writer.write_to_file(log_entry_str)
        row.data = new_data
        row.is_dirty = True
        print(f"[Buffer] Data {key} modified & logged.")
        return report
    
    ''' Manajemen Ukuran Buffer '''
    def _add_to_buffer(self, row: BufferedRow, key:tuple):
        if len(self.buffer_data) >= self.capacity:
            self._evict_block()
        self.buffer_data[key] = row
        self._update_lru(key)

    def _evict_block(self):
        # Logika untuk mengeluarkan blok dari buffer.
        while self.lru_order:
            lru_key = self.lru_order[0]
            row = self.buffer_data[lru_key]
            if not row.is_pinned:
                if row.is_dirty:
                    print(f"[Buffer] Eviction trigger flush for dirty block {lru_key}...")
                    self.flush_dirty_blocks() 
                    continue
                self.lru_order.pop(0)
                self.buffer_data.pop(lru_key)
                return
            else:
                self.lru_order.pop(0)
                self.lru_order.append(lru_key)
    def is_buffer_full(self) -> bool:
        # Mendeteksi kapan buffer sudah penuh
        return len(self.buffer_data) == self.capacity
    
    def is_buffer_almost_full(self) -> bool:
        # Mendeteksi kapan buffer hampir penuh (misalnya 75%)
        return len(self.buffer_data) >= (self.capacity*0.75)
    
    ''' Logika Flush Buffer '''
    def flush_dirty_blocks(self):
        # Menulis semua data 'kotor' di buffer ke disk dan dipanggil saat checkpoint
        dirty_rows = [row for row in self.buffer_data.values() if row.is_dirty]
        if not dirty_rows:
            print("[Buffer] Flush: Tidak ada blok kotor.")
            return
        print(f"[Buffer] Menyiapkan {len(dirty_rows)} blok kotor untuk disimpan (Table-Level)...")
        table_map = {}
        dirty_table_names = set(row.table_name for row in dirty_rows)
        for key, row in self.buffer_data.items():
            t_name = row.table_name
            if t_name in dirty_table_names:
                if t_name not in table_map:
                    table_map[t_name] = []
                table_map[t_name].append(row.data)
                row.is_dirty = False
        self.tables = []
        for t_name, data_list in table_map.items():
            table_obj = TableWrapper(t_name, data_list)
            self.tables.append(table_obj)
        self.save_buffer_callback(self) # type: ignore
        print(f"[Buffer] Flush selesai. Tabel yang disimpan: {list(dirty_table_names)}")
        self.tables = []
        self.clear_buffer()
    
    def clear_buffer(self):
        self.buffer_data.clear()
        self.lru_order.clear()
        print(f"[Buffer Manager] Buffer dikosongkan.")
        
    def write_to_buffer_for_recovery(self, table_name: str, pk_value: Dict[str, Any], new_data: dict) -> None:
        key = self._get_buffer_key(table_name, pk_value)
        pk_str = " | ".join([f"{k}:{v}" for k, v in pk_value.items()])
        
        if key in self.buffer_data:
            row = self.buffer_data[key]
            row.data = new_data
            row.is_dirty = True
            self._update_lru(key)
            print(f"[Buffer Recovery] Updated {table_name} [{pk_str}] in buffer")
        else:
            try:
                disk_data = self.fetch_block_callback(table_name, pk_value)
                if disk_data:
                    row = BufferedRow(table_name, pk_value, new_data, is_dirty=True)
                    self._add_to_buffer(row, key)
                    print(f"[Buffer Recovery] Loaded and updated {table_name} [{pk_str}]")
                else:
                    row = BufferedRow(table_name, pk_value, new_data, is_dirty=True)
                    self._add_to_buffer(row, key)
                    print(f"[Buffer Recovery] Inserted new {table_name} [{pk_str}]")
            except Exception as e:
                row = BufferedRow(table_name, pk_value, new_data, is_dirty=True)
                self._add_to_buffer(row, key)
                print(f"[Buffer Recovery] Inserted new {table_name} [{pk_str}] (disk read failed)")
    
    def delete_from_buffer_for_recovery(self, table_name: str, pk_value: Dict[str, Any]) -> None:
        key = self._get_buffer_key(table_name, pk_value)
        pk_str = " | ".join([f"{k}:{v}" for k, v in pk_value.items()])
        
        if key in self.buffer_data:
            self.buffer_data.pop(key)
            self.lru_order.remove(key)
            print(f"[Buffer Recovery] Deleted {table_name} [{pk_str}] from buffer")
        else:
            try:
                disk_data = self.fetch_block_callback(table_name, pk_value)
                if disk_data:
                    row = BufferedRow(table_name, pk_value, None, is_dirty=True)
                    self._add_to_buffer(row, key)
                    print(f"[Buffer Recovery] Marked {table_name} [{pk_str}] for deletion")
                else:
                    print(f"[Buffer Recovery] {table_name} [{pk_str}] not found (already deleted)")
            except Exception as e:
                print(f"[Buffer Recovery] Warning: Could not delete {table_name} [{pk_str}]: {e}")