import unittest
import os
import time # Tambahkan untuk memastikan timestamp log berubah
from typing import Dict, Any, List, Union

# Impor Komponen Failure Recovery
from buffer_manager import BufferManager
from row_dataclass import BufferedRow
from log_writer import LogWriter
from log_config import MockChangeReport, ActionType

# Variabel Global Disk Data
MOCK_DISK_DATA: Dict[str, Dict[str, Any]] = {} 

class MockTable:
    def __init__(self, name: str, data: List[Dict[str, Any]], pk_column: str = "StudentID"):
        self.name = name
        self.data = data
        self.pk_column = pk_column

def fetch_block_adapter(table_name: str, pk_value: Dict[str, Any]) -> Union[dict, None]:
    global MOCK_DISK_DATA 
    pk_key = next(iter(pk_value))
    key_str = f"{table_name}|{pk_key}:{pk_value[pk_key]}"
    data = MOCK_DISK_DATA.get(key_str)
    return data if data else None

def write_block_adapter(buffered_row: BufferedRow):
    global MOCK_DISK_DATA 
    pk_key = next(iter(buffered_row.primary_key_value))
    pk_val = buffered_row.primary_key_value[pk_key]
    key_str = f"{buffered_row.table_name}|{pk_key}:{pk_val}"
    MOCK_DISK_DATA[key_str] = buffered_row.data.copy() 

def read_table_adapter(table_name: str) -> MockTable:
    global MOCK_DISK_DATA
    rows = [v.copy() for k, v in MOCK_DISK_DATA.items() if k.startswith(table_name)]
    pk = "StudentID" if table_name == "student" else "CourseID"
    return MockTable(name=table_name, data=rows, pk_column=pk)

def write_table_adapter(buffered_rows_list: List[BufferedRow]):
    dirty_count = 0
    for row in buffered_rows_list:
        if row.is_dirty:
            write_block_adapter(row)
            dirty_count += 1

class TestFRMBufferIntegration(unittest.TestCase):
    def setUp(self):
        global MOCK_DISK_DATA
        MOCK_DISK_DATA = {
            "student|StudentID:1": {"StudentID": 1, "FullName": "Alice", "GPA": 3.8, "stock": 100},
            "student|StudentID:2": {"StudentID": 2, "FullName": "Bob", "GPA": 3.5, "stock": 50},
            "course|CourseID:101": {"CourseID": 101, "Name": "DB", "Year": 2025},
        }
        self.log_dir = "temp_test_logs"
        os.makedirs(self.log_dir, exist_ok=True)
        
        for f in os.listdir(self.log_dir):
            os.remove(os.path.join(self.log_dir, f))
        time.sleep(0.01) 
            
        self.log_writer = LogWriter(log_directory=self.log_dir)
        self.log_writer.active_logfile = None
        self.buffer_mgr = BufferManager(log_writer=self.log_writer, capacity=2) # Kapasitas kecil untuk uji LRU
        
        self.buffer_mgr.set_fetch_block_routine(fetch_block_adapter)
        self.buffer_mgr.set_write_block_routine(write_block_adapter)
        self.buffer_mgr.set_read_table_routine(read_table_adapter)
        self.buffer_mgr.set_write_table_routine(write_table_adapter) 
        

    def tearDown(self):
        self.buffer_mgr.clear_buffer()
        if os.path.exists(self.log_dir):
             for f in os.listdir(self.log_dir):
                os.remove(os.path.join(self.log_dir, f))
             os.rmdir(self.log_dir)


    def test_load_all_rows_of_table_success(self):
        T_NAME = "student"
        PK_COL = "StudentID"
        self.buffer_mgr.load_all_rows_of_table(T_NAME, PK_COL)
        self.assertEqual(len(self.buffer_mgr.buffer_data), 2, "Harusnya ada 2 blok student di buffer.")
        key_1 = self.buffer_mgr._get_buffer_key(T_NAME, {PK_COL: 1})
        self.assertEqual(self.buffer_mgr.buffer_data[key_1].data['GPA'], 3.8) 

    def test_wal_and_eviction(self):
        T_NAME = "student"
        self.buffer_mgr.write_block(100, T_NAME, {"StudentID": 1}, {"StudentID": 1, "GPA": 4.0, "stock": 100})
        self.buffer_mgr.write_block(101, T_NAME, {"StudentID": 2}, {"StudentID": 2, "GPA": 3.0, "stock": 50})
        active_log_file = self.log_writer._get_active_logfile() 
        with open(active_log_file, 'r') as f:
            log_content = f.read()
        search_string = '"transaction_id": 100'
        self.assertTrue(search_string in log_content, 
                        f"Log entry for TID 100 tidak ditemukan dalam log. Isi log: {log_content}")

        global MOCK_DISK_DATA
        MOCK_DISK_DATA["student|StudentID:3"] = {"StudentID": 3, "FullName": "Charlie", "GPA": 2.5, "stock": 0}
        # Block 1 (StudentID:1) di-evict (ditulis ke disk)
        self.buffer_mgr.write_block(102, T_NAME, {"StudentID": 3}, {"StudentID": 3, "GPA": 2.5, "stock": 0})
        # Verifikasi Eviction
        key_1 = self.buffer_mgr._get_buffer_key(T_NAME, {"StudentID": 1})
        self.assertNotIn(key_1, self.buffer_mgr.buffer_data, "Blok 1 seharusnya sudah di-evict (karena LRU).")
        self.assertEqual(len(self.buffer_mgr.buffer_data), 2, "Buffer harus tetap berukuran 2 (blok 2 dan 3).")
        # Verifikasi Durability: StudentID 1 harus memiliki GPA 4.0 di disk (karena di-evict)
        self.assertEqual(MOCK_DISK_DATA["student|StudentID:1"]['GPA'], 4.0)

    def test_flush_dirty_blocks(self):
        T_NAME = "student"
        self.buffer_mgr.write_block(100, T_NAME, {"StudentID": 1}, {"StudentID": 1, "GPA": 4.0, "stock": 99})
        self.buffer_mgr.flush_dirty_blocks()
        self.assertEqual(len(self.buffer_mgr.buffer_data), 0, "Buffer harus kosong setelah flush dan clear.")
        disk_key = "student|StudentID:1"
        self.assertEqual(MOCK_DISK_DATA[disk_key]['GPA'], 4.0, "Data harus terupdate di mock disk.")


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)