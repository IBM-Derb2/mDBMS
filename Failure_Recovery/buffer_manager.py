from typing import Dict, Any, Union, List
from row_dataclass import BufferedRow, BUFFER_CAPACITY
from log_config import MockChangeReport
from log_writer import LogWriter


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
        self.tables = [] 
    
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
            try:
                self.read_block(table_name, pk_value)
            except FileNotFoundError:
                try: 
                    self.load_table_callback(table_name)
                except: 
                    pass
                new_row = BufferedRow(table_name, pk_value, {}, is_dirty=True)
                self._add_to_buffer(new_row, key)

        row = self.buffer_data[key]
        self._update_lru(key)
        
        old_data = row.data.copy()
        self.log_writer.log_operation(
            tx_id=transaction_id,
            table=table_name,
            pk=pk_value,
            old_data=old_data if old_data else None, # Pastikan None jika kosong
            new_data=new_data
        )
        
        row.data = new_data
        row.is_dirty = True
        print(f"[Buffer] Data {key} modified & logged.")
        return MockChangeReport(table_name, pk_value, old_data, new_data)

    def _add_to_buffer(self, row: BufferedRow, key:tuple):
        if len(self.buffer_data) >= self.capacity:
            self._evict_block()
        self.buffer_data[key] = row
        self._update_lru(key)

    def _evict_block(self):
        while self.lru_order:
            lru_key = self.lru_order[0]
            row = self.buffer_data[lru_key]
            if not row.is_pinned:
                if row.is_dirty:
                    self.flush_dirty_blocks() 
                    continue 
                self.lru_order.pop(0)
                self.buffer_data.pop(lru_key)
                return
            else:
                self.lru_order.pop(0)
                self.lru_order.append(lru_key)

    def is_buffer_almost_full(self) -> bool:
        # Mendeteksi kapan buffer hampir penuh (misalnya 75%)
        return len(self.buffer_data) >= (self.capacity*0.75)
    
    ''' Logika Flush Buffer '''
    def flush_dirty_blocks(self):
        dirty_rows = [row for row in self.buffer_data.values() if row.is_dirty]
        if not dirty_rows:
            self.clear_buffer()
            return
        print(f"[Buffer] Menyiapkan {len(dirty_rows)} blok kotor. Melakukan Merge dengan Disk...")
        dirty_table_names = set(row.table_name for row in dirty_rows)
        self.tables = []

        for t_name in dirty_table_names:
            current_disk_data = []
            try:
                table_obj = self.load_table_callback(t_name)
                if table_obj and hasattr(table_obj, 'data'):
                    current_disk_data = table_obj.data
            except:
                pass # Tabel baru
            
            final_rows = []
            buffer_updates = [r for r in dirty_rows if r.table_name == t_name]
            processed_buffer_keys = set()
            
            for disk_row in current_disk_data:
                updated_row = disk_row
                
                for buf_row in buffer_updates:
                    is_match = True
                    for k, v in buf_row.primary_key_value.items():
                        if disk_row.get(k) != v:
                            is_match = False
                            break
                    
                    if is_match:
                        updated_row = buf_row.data
                        key = self._get_buffer_key(t_name, buf_row.primary_key_value)
                        processed_buffer_keys.add(key)
                        buf_row.is_dirty = False # Tandai sudah diproses
                        break
                
                final_rows.append(updated_row)
            
            for buf_row in buffer_updates:
                key = self._get_buffer_key(t_name, buf_row.primary_key_value)
                if key not in processed_buffer_keys:
                    final_rows.append(buf_row.data)
                    buf_row.is_dirty = False

            self.tables.append(TableWrapper(t_name, final_rows))
            
        self.save_buffer_callback(self)
        
        print(f"[Buffer] Flush & Merge selesai. Tabel: {list(dirty_table_names)}")
        self.tables = []
        self.clear_buffer()
    
    def clear_buffer(self):
        self.buffer_data.clear()
        self.lru_order.clear()
        print(f"[Buffer Manager] Buffer dikosongkan.")
        
    def write_to_buffer_for_recovery(self, table_name: str, pk_value: Dict[str, Any], new_data: dict) -> None:
        key = self._get_buffer_key(table_name, pk_value)
        
        row = BufferedRow(table_name, pk_value, new_data, is_dirty=True)
        if len(self.buffer_data) >= self.capacity and key not in self.buffer_data:
             self._evict_block()
        
        self.buffer_data[key] = row
        self._update_lru(key)
        print(f"[Buffer Recovery] RE-APPLIED {table_name} {pk_value}")
    
    def delete_from_buffer_for_recovery(self, table_name: str, pk_value: Dict[str, Any]) -> None:
        key = self._get_buffer_key(table_name, pk_value)
        if key in self.buffer_data:
            self.buffer_data.pop(key)
            if key in self.lru_order: self.lru_order.remove(key)
            print(f"[Buffer Recovery] UNDO DELETE {table_name} {pk_value}")