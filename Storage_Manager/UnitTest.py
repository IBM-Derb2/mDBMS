import unittest
import time
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Storage_Manager.storage_engine import StorageEngine
from Storage_Manager.utils import DataRetrieval, Condition, DataWrite, DataDeletion
from Storage_Manager.serializer import Serializer
from Storage_Manager.hash_index import HashIndex
from Storage_Manager.b_plus_tree_index import BPlusTreeIndex
from Failure_Recovery.buffer_manager import BufferManager
from Failure_Recovery.failure_recovery_manager import FailureRecoveryManager


class TestStorageEngine(unittest.TestCase): # Main runs all methods that start with 'test_'
    
    DATA_DIR = "Storage_Manager"
    
    @classmethod
    def setUpClass(cls):
        cls.serializer = Serializer()
        cls.storage = StorageEngine(data_dir=cls.DATA_DIR, serializer=cls.serializer)
        
        buffer_manager = BufferManager(capacity=100)
        cls.frm = FailureRecoveryManager(
            buffer_manager=buffer_manager,
            load_table_callback=cls.storage.read_disk_to_buffer,
            save_buffer_callback=cls.storage.save_buffer_to_disk,
            log_directory="test_logs"
        )
        cls.storage.frm = cls.frm

    def test_get_stats(self):
        stats = self.storage.get_stats("student")

        self.assertIsNotNone(stats)
        print(f"Test get_stats:\n{stats}")

    def test_index_performance_hash(self):
        TABLE_NAME = "student"
        COLUMN_NAME = "gpa"
        TARGET_VALUE = 4.0
        ITERATIONS = 100

        condition = [Condition(column=COLUMN_NAME, operation="=", operand=TARGET_VALUE)]

        print(f"\nTest index_performance_hash:\nStarting benchmark ({ITERATIONS} iterations)")

        # cleanup any existing indexes
        idx_file = f"data/{self.DATA_DIR}/{TABLE_NAME}_{COLUMN_NAME}_hash.dat"
        if os.path.exists(idx_file):
            HashIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)

        btree_file = f"data/{self.DATA_DIR}/{TABLE_NAME}_{COLUMN_NAME}_btree.dat"
        if os.path.exists(btree_file):
            BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)

        start_idx = time.perf_counter()
        HashIndex.create(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)
        end_idx = time.perf_counter()

        self.assertTrue(os.path.exists(idx_file))
        size_kb = os.path.getsize(idx_file) / 1024
        print(f"Index created: {(end_idx - start_idx)*1000:.4f}ms, {size_kb:.2f}KB")

        dr_linear = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=condition,
            search_type="linear"
        )

        linear_times = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            res_linear = self.storage.read_block(dr_linear)
            end = time.perf_counter()
            linear_times.append((end - start) * 1000)

        linear_avg = sum(linear_times) / len(linear_times)
        linear_min = min(linear_times)
        linear_count = res_linear.rows_count

        print(f"Linear scan: {linear_avg:.4f}ms avg, {linear_min:.4f}ms min, {linear_count} rows")
        
        dr_index = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=condition,
            search_type="index",
            index_column=COLUMN_NAME
        )

        index_times = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            res_index = self.storage.read_block(dr_index)
            end = time.perf_counter()
            index_times.append((end - start) * 1000)

        index_avg = sum(index_times) / len(index_times)
        index_min = min(index_times)
        index_count = res_index.rows_count

        print(f"Index scan: {index_avg:.4f}ms avg, {index_min:.4f}ms min, {index_count} rows")

        self.assertEqual(linear_count, index_count)

        speedup = linear_avg / index_avg
        print(f"Speedup: {speedup:.2f}x faster\n")

        # cleanup
        HashIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)
        print(f"Cleanup: Hash index deleted")

    def test_index_performance_btree(self):
        TABLE_NAME = "student"
        COLUMN_NAME = "gpa"
        MIN_VALUE = 3.8
        MAX_VALUE = 3.85
        ITERATIONS = 100

        conditions = [
            Condition(column=COLUMN_NAME, operation=">", operand=MIN_VALUE),
            Condition(column=COLUMN_NAME, operation="<", operand=MAX_VALUE)
        ]

        print(f"\nTest index_performance_btree (range query {MIN_VALUE} < gpa < {MAX_VALUE}):\nStarting benchmark ({ITERATIONS} iterations)")

        # cleanup
        hash_idx_file = f"data/{self.DATA_DIR}/{TABLE_NAME}_{COLUMN_NAME}_hash.dat"
        if os.path.exists(hash_idx_file):
            HashIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)

        idx_file = f"data/{self.DATA_DIR}/{TABLE_NAME}_{COLUMN_NAME}_btree.dat"
        if os.path.exists(idx_file):
            BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)

        start_idx = time.perf_counter()
        BPlusTreeIndex.create(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR, order=5)
        end_idx = time.perf_counter()

        self.assertTrue(os.path.exists(idx_file))
        size_kb = os.path.getsize(idx_file) / 1024
        print(f"B+ Tree index created: {(end_idx - start_idx)*1000:.4f}ms, {size_kb:.2f}KB")

        dr_linear = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=conditions,
            search_type="linear"
        )

        linear_times = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            res_linear = self.storage.read_block(dr_linear)
            end = time.perf_counter()
            linear_times.append((end - start) * 1000)

        linear_avg = sum(linear_times) / len(linear_times)
        linear_min = min(linear_times)
        linear_count = res_linear.rows_count

        print(f"Linear scan: {linear_avg:.4f}ms avg, {linear_min:.4f}ms min, {linear_count} rows")

        dr_index = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=conditions,
            search_type="index",
            index_column=COLUMN_NAME
        )

        index_times = []
        for _ in range(ITERATIONS):
            start = time.perf_counter()
            res_index = self.storage.read_block(dr_index)
            end = time.perf_counter()
            index_times.append((end - start) * 1000)

        index_avg = sum(index_times) / len(index_times)
        index_min = min(index_times)
        index_count = res_index.rows_count

        print(f"B+ Tree index scan: {index_avg:.4f}ms avg, {index_min:.4f}ms min, {index_count} rows")

        self.assertEqual(linear_count, index_count)

        speedup = linear_avg / index_avg
        print(f"B+ Tree Speedup: {speedup:.2f}x faster\n")

        # cleanup: delete the B+ tree index
        BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)
        print(f"Cleanup: B+ Tree index deleted")

    def test_read_block(self):
        print(f"\nTest read_block:")
        dr = DataRetrieval(
            table="student",
            column=["studentid", "fullname", "gpa"],
            conditions=[Condition("gpa", ">", 3.5)]
        )
        print(f"Conditions: {dr.conditions}")
        rows = self.storage.read_block(dr)

        print(f"Rows found: {rows.rows_count}")
        if rows.rows_count > 0:
            print(f"Sample rows: {rows.data[:3]}")

        self.assertGreater(rows.rows_count, 0)
        print(f"Test read_block: {rows.rows_count} rows found (gpa > 3.5)")

    def test_btree_with_dml(self):
        print(f"\n===== Test B+ Tree with DML =====")
        
        TABLE_NAME = "student"
        COLUMN_NAME = "gpa"
        
        # Clean up any existing indexes (hash or btree)
        hash_file = f"data/{self.DATA_DIR}/{TABLE_NAME}_{COLUMN_NAME}_hash.dat"
        btree_file = f"data/{self.DATA_DIR}/{TABLE_NAME}_{COLUMN_NAME}_btree.dat"
        if os.path.exists(hash_file):
            HashIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)
        if os.path.exists(btree_file):
            BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)
        
        BPlusTreeIndex.create(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR, order=5)
        
        # student 1's current gpa
        check_dr = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=[Condition("studentid", "=", 1)],
            search_type="linear"
        )
        student_1 = self.storage.read_block(check_dr).data[0]
        original_gpa = student_1['gpa']
        print(f"[1/4] Student 1 gpa: {original_gpa}")
        
        # count rows with gpa=2.75
        dr = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=[Condition(COLUMN_NAME, "=", 2.75)],
            search_type="index",
            index_column=COLUMN_NAME
        )
        before = self.storage.read_block(dr).rows_count
        print(f"[2/4] Before UPDATE: {before} rows with gpa=2.75")
        
        # update Student 1 to gpa=2.75
        write_result = self.storage.write_block(DataWrite(
            table=TABLE_NAME,
            column=["gpa"],
            new_value=2.75,
            conditions=[Condition("studentid", "=", 1)]
        ))
        print(f"    UPDATE affected {write_result} row(s)")
        
        # Flush buffer to ensure changes are written
        self.storage.frm.buffer_manager.flush_dirty_blocks()
        
        after = self.storage.read_block(dr).rows_count
        print(f"[3/4] After UPDATE: {after} rows (index auto-updated)")
        
        linear_dr = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=[Condition(COLUMN_NAME, "=", 2.75)],
            search_type="linear"
        )
        linear_count = self.storage.read_block(linear_dr).rows_count
        print(f"[4/4] Linear scan: {linear_count} rows")
        
        print(f"    Debug: original_gpa={original_gpa}, before={before}, after={after}, linear={linear_count}")
        
        if original_gpa != 2.75:
            # Index should reflect the change
            self.assertEqual(after, linear_count, "Index should match linear scan after UPDATE")
        else:
            self.assertEqual(after, before, "No change if same value")
        self.assertEqual(after, linear_count, "Index matches linear")
        
        BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)
        print(f"===== Test Complete =====\n")

    def test_buffer_communication(self):
        # Use buffer_manager from the FRM already set up in setUp()
        buffer_manager = self.storage.frm.buffer_manager

        # Test 1: Cache MISS
        pk_value_1 = {"studentid": 1}
        row_1 = buffer_manager.read_block("student", pk_value_1)
        self.assertIsNotNone(row_1)
        self.assertFalse(row_1.is_dirty)
        print(f"[1/7] Cache miss: loaded from disk")

        # Test 2: Cache HIT
        row_1_cached = buffer_manager.read_block("student", pk_value_1)
        self.assertEqual(row_1.data, row_1_cached.data)
        print(f"[2/7] Cache hit: loaded from buffer")

        # Test 3: WRITE and mark dirty
        new_data = {"studentid": 1, "fullname": "Updated_Student_1", "gpa": 3.99}
        change_report = buffer_manager.write_block(999, "student", pk_value_1, new_data)
        row_after_write = buffer_manager.buffer_data[buffer_manager._get_buffer_key("student", pk_value_1)]
        self.assertTrue(row_after_write.is_dirty)
        print(f"[3/7] Write: buffer marked dirty")

        # Test 4: Buffer capacity and LRU
        for student_id in [2, 3, 4]:
            buffer_manager.read_block("student", {"studentid": student_id})
        self.assertEqual(len(buffer_manager.buffer_data), 4)
        print(f"[4/7] Buffer at capacity: {len(buffer_manager.buffer_data)} entries")

        # Test 5: Flush dirty blocks
        dirty_count = sum(1 for block in buffer_manager.buffer_data.values() if block.is_dirty)
        buffer_manager.flush_dirty_blocks()
        dirty_after = sum(1 for block in buffer_manager.buffer_data.values() if block.is_dirty)
        print(f"[5/7] Flush: {dirty_count} dirty blocks before, {dirty_after} after")
        self.assertEqual(dirty_after, 0, "All dirty blocks should be flushed")

        # Test 6: Callback registration
        self.assertIsNotNone(buffer_manager.load_table_callback)
        self.assertIsNotNone(buffer_manager.save_buffer_callback)
        print(f"[6/7] Callbacks registered")

        # Test 7: FRM integration
        self.assertIsNotNone(self.storage.frm)
        self.assertEqual(self.storage.frm.buffer_manager, buffer_manager)
        print(f"[7/7] FRM integrated with StorageEngine")

    def test_buffer_range_query(self):
        print(f"\nTest buffer_range_query:")

        # Use the buffer_manager from setUp()
        buffer_manager = self.storage.frm.buffer_manager

        # adjust students in buffer
        buffer_manager.write_block(100, "student", {"studentid": 1},
                                   {"studentid": 1, "fullname": "Modified_1", "gpa": 4.0})
        buffer_manager.write_block(100, "student", {"studentid": 3},
                                   {"studentid": 3, "fullname": "Modified_3", "gpa": 3.5})

        # query range that includes modified rows
        dr = DataRetrieval(table="student", column=["*"],
                          conditions=[Condition("studentid", "<=", 5)])
        rows = self.storage.read_block(dr)

        student_1 = [r for r in rows.data if r['studentid'] == 1][0]
        student_3 = [r for r in rows.data if r['studentid'] == 3][0]

        self.assertEqual(student_1['fullname'], "Modified_1")
        self.assertEqual(student_1['gpa'], 4.0)
        self.assertEqual(student_3['fullname'], "Modified_3")
        self.assertEqual(student_3['gpa'], 3.5)

        print(f"Range query merged buffer data: PASS")

    def test_primary_key_uniqueness(self):
        """Test primary key uniqueness and verify index maintenance for INSERT and DELETE operations"""
        TABLE_NAME = "student"
        COLUMN_NAME = "gpa"

        print(f"\nTest primary_key_uniqueness:\nVerifying PK constraint + index maintenance (INSERT/DELETE)")

        # Create B+ tree index on gpa for testing
        idx_file = f"data/{self.DATA_DIR}/{TABLE_NAME}_{COLUMN_NAME}_btree.dat"
        if os.path.exists(idx_file):
            BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)
        BPlusTreeIndex.create(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR, order=5)
        print(f"[Setup] B+ tree index created on {COLUMN_NAME}")

        print(f"[1/5] Attempting to insert duplicate studentid=1 (exists on disk)...")
        try:
            duplicate_write = DataWrite(
                table=TABLE_NAME,
                column=["studentid", "fullname", "gpa"],
                conditions=[],
                new_value=[1, "Duplicate_Student", 3.5]
            )
            self.storage.write_block(duplicate_write)
            self.fail("Should have raised ValueError for duplicate primary key")
        except ValueError as e:
            self.assertIn("Primary key violation", str(e))
            print(f"    Correctly rejected: {e}")

        print(f"[2/5] Inserting new unique studentid=99999 with gpa=3.8...")
        try:
            unique_write = DataWrite(
                table=TABLE_NAME,
                column=["studentid", "fullname", "gpa"],
                conditions=[],
                new_value=[99999, "Test_Student", 3.8]
            )
            rows_affected = self.storage.write_block(unique_write)
            self.assertEqual(rows_affected, 1)
            print(f"    Successfully inserted unique record")
            
            # Flush buffer to write to disk so index scan can find it
            self.storage.frm.buffer_manager.flush_dirty_blocks()
        except Exception as e:
            self.fail(f"Unexpected error on unique insert: {e}")

        # Verify index was updated after INSERT
        dr_gpa_38 = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=[Condition(COLUMN_NAME, "=", 3.8)],
            search_type="index",
            index_column=COLUMN_NAME
        )
        idx_count_insert = self.storage.read_block(dr_gpa_38).rows_count
        print(f"    Index verification: {idx_count_insert} rows with gpa=3.8 (should include new record)")
        self.assertGreaterEqual(idx_count_insert, 1, "Index should contain the inserted row")

        print(f"[3/5] Attempting to insert duplicate studentid=99999...")
        try:
            duplicate_write_2 = DataWrite(
                table=TABLE_NAME,
                column=["studentid", "fullname", "gpa"],
                conditions=[],
                new_value=[99999, "Another_Duplicate", 3.6]
            )
            self.storage.write_block(duplicate_write_2)
            self.fail("Should have raised ValueError for duplicate primary key")
        except ValueError as e:
            self.assertIn("Primary key violation", str(e))
            print(f"    Correctly rejected: {e}")

        print(f"[4/5] Removing test record studentid=99999...")
        deletion = DataDeletion(
            table=TABLE_NAME,
            conditions=[Condition("studentid", "=", 99999)]
        )
        
        # Flush buffer first to ensure the record is on disk before deletion
        self.storage.frm.buffer_manager.flush_dirty_blocks()
        
        deleted_count = self.storage.delete_block(deletion)
        print(f"    Deleted {deleted_count} row(s)")
        
        # Flush again after deletion to ensure index updates are persisted
        self.storage.frm.buffer_manager.flush_dirty_blocks()
        
        # Verify deletion with a read
        verify_dr = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=[Condition("studentid", "=", 99999)]
        )
        remaining = self.storage.read_block(verify_dr).rows_count
        print(f"    Verification: {remaining} rows remaining with studentid=99999")
        
        self.assertEqual(remaining, 0, "Record should be deleted")
        print(f"    Test record deleted successfully")

        # Verify index was updated after DELETE
        print(f"[5/5] Verifying index maintenance after DELETE...")
        idx_count_after_delete = self.storage.read_block(dr_gpa_38).rows_count
        print(f"    Index verification: {idx_count_after_delete} rows with gpa=3.8 after deletion")
        self.assertEqual(idx_count_after_delete, idx_count_insert - 1, 
                        "Index should have one less entry after DELETE")
        print(f"    Index correctly updated (had {idx_count_insert}, now {idx_count_after_delete})")

        # Cleanup index
        BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME, data_dir=self.DATA_DIR)
        print(f"[Cleanup] B+ tree index dropped")


if __name__ == "__main__":
    verbosity = 0

    if len(sys.argv) > 1:
        try:
            v = int(sys.argv[1])
            if v in (0, 1, 2):
                verbosity = v
        except ValueError:
            pass  

        sys.argv = sys.argv[:1]

    unittest.main(verbosity=verbosity)
