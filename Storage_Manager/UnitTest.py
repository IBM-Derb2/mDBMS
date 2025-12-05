import unittest
import time
import os
import random
import sys

from .storage_engine import StorageEngine
from .utils import DataRetrieval, Condition, DataWrite
from .serializer import Serializer
from .hash_index import HashIndex
from .b_plus_tree_index import BPlusTreeIndex

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from Failure_Recovery.buffer_manager import BufferManager
from Failure_Recovery.failure_recovery_manager import FailureRecoveryManager


class TestStorageEngine(unittest.TestCase): # Main runs all methods that start with 'test_'
    
    @classmethod
    def setUpClass(cls):
        print("\nSetup: Generating test data")

        random.seed(2025)
        cls.serializer = Serializer()

        # Create StorageEngine first (without FRM)
        cls.storage = StorageEngine(serializer=cls.serializer)

        # Initialize FRM with StorageEngine callbacks
        buffer_manager = BufferManager(capacity=100)
        cls.frm = FailureRecoveryManager(
            buffer_manager=buffer_manager,
            load_table_callback=cls.storage.read_disk_to_buffer,
            save_buffer_callback=cls.storage.save_buffer_to_disk,
            log_directory="test_logs"
        )

        # Inject FRM into StorageEngine
        cls.storage.frm = cls.frm

        schema_student = {
            "table_name": "student",
            "columns": [
                {"name": "StudentID", "type": "int"},
                {"name": "FullName", "type": "varchar", "length": 50},
                {"name": "GPA", "type": "float"}
            ]
        }

        schema_course = {
            "table_name": "course",
            "columns": [
                {"name": "CourseID", "type": "int"},
                {"name": "Year", "type": "int"},
                {"name": "CourseName", "type": "varchar", "length": 50},
                {"name": "CourseDescription", "type": "varchar", "length": 255}
            ]
        }

        schema_attends = {
            "table_name": "attends",
            "columns": [
                {"name": "StudentID", "type": "int"},
                {"name": "CourseID", "type": "int"},
                {"name": "Year", "type": "int"},
            ]
        }

        students = [
            {
                "StudentID": i,
                "FullName": f"Student_{i}",
                "GPA": round(random.uniform(2.0, 4.0), 2)
            }
            for i in range(1, 10001)
        ]

        courses = [
            {
                "CourseID": i,
                "Year": random.choice([2023, 2024, 2025]),
                "CourseName": f"Course_{i}",
                "CourseDescription": f"This is a description for course {i}. It covers topic {random.randint(1,10)} and includes several exercises."
            }
            for i in range(1, 51)
        ]

        attends = [
            {
                "StudentID": random.randint(1, 10000),
                "CourseID": random.randint(1, 50),
                "Year": random.choice([2023, 2024, 2025])
            }
            for _ in range(50)
        ]

        for schema, data in [
            (schema_student, students),
            (schema_course, courses),
            (schema_attends, attends)
        ]:
            cls.storage.write_schema_file(schema)
            cls.storage.write_data_file(schema["table_name"], data, schema)

        print("Setup: Complete (10000 students, 50 courses, 50 attends)\n")

    def setUp(self):
        self.serializer = Serializer()
        self.storage = StorageEngine(serializer=self.serializer)

        # Initialize FRM for each test
        buffer_manager = BufferManager(capacity=100)
        frm = FailureRecoveryManager(
            buffer_manager=buffer_manager,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory="test_logs"
        )
        self.storage.frm = frm

    def test_get_stats(self):
        stats = self.storage.get_stats("student")

        self.assertIsNotNone(stats)
        print(f"Test get_stats:\n{stats}")

    def test_index_performance_hash(self):
        TABLE_NAME = "student"
        COLUMN_NAME = "GPA"
        TARGET_VALUE = 4.0
        ITERATIONS = 100

        condition = [Condition(column=COLUMN_NAME, operation="=", operand=TARGET_VALUE)]

        print(f"\nTest index_performance_hash:\nStarting benchmark ({ITERATIONS} iterations)")

        idx_file = f"data/{TABLE_NAME}_{COLUMN_NAME}_hash.dat"
        if os.path.exists(idx_file):
            HashIndex.drop(TABLE_NAME, COLUMN_NAME)

        start_idx = time.perf_counter()
        HashIndex.create(TABLE_NAME, COLUMN_NAME)
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

        self.assertGreater(speedup, 1.0)

        # cleanup
        HashIndex.drop(TABLE_NAME, COLUMN_NAME)
        print(f"Cleanup: Hash index deleted")

    def test_index_performance_btree(self):
        TABLE_NAME = "student"
        COLUMN_NAME = "GPA"
        TARGET_VALUE = 3.75
        ITERATIONS = 100

        conditions = [Condition(column=COLUMN_NAME, operation="=", operand=TARGET_VALUE)]

        print(f"\nTest index_performance_btree:\\nStarting benchmark ({ITERATIONS} iterations)")

        # cleanup
        hash_idx_file = f"data/{TABLE_NAME}_{COLUMN_NAME}_hash.dat"
        if os.path.exists(hash_idx_file):
            HashIndex.drop(TABLE_NAME, COLUMN_NAME)

        idx_file = f"data/{TABLE_NAME}_{COLUMN_NAME}_btree.dat"
        if os.path.exists(idx_file):
            BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME)

        start_idx = time.perf_counter()
        BPlusTreeIndex.create(TABLE_NAME, COLUMN_NAME, order=5)
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

        self.assertGreater(speedup, 1.0)

        # cleanup: delete the B+ tree index
        BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME)
        print(f"Cleanup: B+ Tree index deleted")

    def test_read_block(self):
        print(f"\nTest read_block:")
        dr = DataRetrieval(
            table="student",
            column=["StudentID", "FullName", "GPA"],
            conditions=[Condition("GPA", ">", 3.5)]
        )
        print(f"Conditions: {dr.conditions}")
        rows = self.storage.read_block(dr)

        print(f"Rows found: {rows.rows_count}")
        if rows.rows_count > 0:
            print(f"Sample rows: {rows.data[:3]}")

        self.assertGreater(rows.rows_count, 0)
        print(f"Test read_block: {rows.rows_count} rows found (GPA > 3.5)")

    def test_btree_with_dml(self):
        print(f"\n===== Test B+ Tree with DML =====")
        
        TABLE_NAME = "student"
        COLUMN_NAME = "GPA"
        
        # Clean up any existing indexes (hash or btree)
        hash_file = f"data/{TABLE_NAME}_{COLUMN_NAME}_hash.dat"
        btree_file = f"data/{TABLE_NAME}_{COLUMN_NAME}_btree.dat"
        if os.path.exists(hash_file):
            HashIndex.drop(TABLE_NAME, COLUMN_NAME)
        if os.path.exists(btree_file):
            BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME)
        
        BPlusTreeIndex.create(TABLE_NAME, COLUMN_NAME, order=5)
        
        # student 1's current GPA
        check_dr = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=[Condition("StudentID", "=", 1)],
            search_type="linear"
        )
        student_1 = self.storage.read_block(check_dr).data[0]
        original_gpa = student_1['gpa']
        print(f"[1/4] Student 1 GPA: {original_gpa}")
        
        # count rows with GPA=2.75
        dr = DataRetrieval(
            table=TABLE_NAME,
            column=["*"],
            conditions=[Condition(COLUMN_NAME, "=", 2.75)],
            search_type="index",
            index_column=COLUMN_NAME
        )
        before = self.storage.read_block(dr).rows_count
        print(f"[2/4] Before UPDATE: {before} rows with GPA=2.75")
        
        # update Student 1 to GPA=2.75
        self.storage.write_block(DataWrite(
            table=TABLE_NAME,
            column=["GPA"],
            new_value=2.75,
            conditions=[Condition("StudentID", "=", 1)]
        ))
        
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
        
        if original_gpa != 2.75:
            self.assertEqual(after, before + 1, "Index should auto-update")
        else:
            self.assertEqual(after, before, "No change if same value")
        self.assertEqual(after, linear_count, "Index matches linear")
        
        BPlusTreeIndex.drop(TABLE_NAME, COLUMN_NAME)
        print(f"===== Test Complete =====\n")

    def test_buffer_communication(self):
        # Use buffer_manager from the FRM already set up in setUp()
        buffer_manager = self.storage.frm.buffer_manager

        # Test 1: Cache MISS
        pk_value_1 = {"StudentID": 1}
        row_1 = buffer_manager.read_block("student", pk_value_1)
        self.assertIsNotNone(row_1)
        self.assertFalse(row_1.is_dirty)
        print(f"[1/7] Cache miss: loaded from disk")

        # Test 2: Cache HIT
        row_1_cached = buffer_manager.read_block("student", pk_value_1)
        self.assertEqual(row_1.data, row_1_cached.data)
        print(f"[2/7] Cache hit: loaded from buffer")

        # Test 3: WRITE and mark dirty
        new_data = {"StudentID": 1, "FullName": "Updated_Student_1", "GPA": 3.99}
        change_report = buffer_manager.write_block(999, "student", pk_value_1, new_data)
        row_after_write = buffer_manager.buffer_data[buffer_manager._get_buffer_key("student", pk_value_1)]
        self.assertTrue(row_after_write.is_dirty)
        print(f"[3/7] Write: buffer marked dirty")

        # Test 4: Buffer capacity and LRU
        for student_id in [2, 3, 4]:
            buffer_manager.read_block("student", {"StudentID": student_id})
        self.assertEqual(len(buffer_manager.buffer_data), 4)
        print(f"[4/7] Buffer at capacity: {len(buffer_manager.buffer_data)} entries")

        # Test 5: Flush dirty blocks
        buffer_manager.flush_dirty_blocks()
        self.assertEqual(len(buffer_manager.buffer_data), 0)
        print(f"[5/7] Flush: dirty blocks written to disk")

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
        buffer_manager.write_block(100, "student", {"StudentID": 1},
                                   {"StudentID": 1, "FullName": "Modified_1", "GPA": 4.0})
        buffer_manager.write_block(100, "student", {"StudentID": 3},
                                   {"StudentID": 3, "FullName": "Modified_3", "GPA": 3.95})

        # query range that includes modified rows
        dr = DataRetrieval(table="student", column=["*"],
                          conditions=[Condition("StudentID", "<=", 5)])
        rows = self.storage.read_block(dr)

        student_1 = [r for r in rows.data if r['studentid'] == 1][0]
        student_3 = [r for r in rows.data if r['studentid'] == 3][0]

        self.assertEqual(student_1['fullname'], "Modified_1")
        self.assertEqual(student_1['gpa'], 4.0)
        self.assertEqual(student_3['fullname'], "Modified_3")
        self.assertEqual(student_3['gpa'], 3.95)

        print(f"Range query merged buffer data: PASS")

    def test_primary_key_uniqueness(self):

        TABLE_NAME = "student"

        print(f"[1/3] Attempting to insert duplicate StudentID=1 (exists on disk)...")
        try:
            duplicate_write = DataWrite(
                table=TABLE_NAME,
                column=["StudentID", "FullName", "GPA"],
                conditions=[],
                new_value=[1, "Duplicate_Student", 3.5]
            )
            self.storage.write_block(duplicate_write)
            self.fail("Should have raised ValueError for duplicate primary key")
        except ValueError as e:
            self.assertIn("Primary key violation", str(e))
            print(f"    Correctly rejected: {e}")

        print(f"[2/3] Inserting new unique StudentID=99999...")
        try:
            unique_write = DataWrite(
                table=TABLE_NAME,
                column=["StudentID", "FullName", "GPA"],
                conditions=[],
                new_value=[99999, "New_Student", 3.8]
            )
            rows_affected = self.storage.write_block(unique_write)
            self.assertEqual(rows_affected, 1)
            print(f"    Successfully inserted unique record")
        except Exception as e:
            self.fail(f"Unexpected error on unique insert: {e}")

        print(f"[3/3] Attempting to insert duplicate StudentID=99999...")
        try:
            duplicate_write_2 = DataWrite(
                table=TABLE_NAME,
                column=["StudentID", "FullName", "GPA"],
                conditions=[],
                new_value=[99999, "Another_Duplicate", 3.2]
            )
            self.storage.write_block(duplicate_write_2)
            self.fail("Should have raised ValueError for duplicate primary key")
        except ValueError as e:
            self.assertIn("Primary key violation", str(e))
            print(f"    Correctly rejected: {e}")

        print(f"[Cleanup] Removing test record StudentID=99999...")
        from .utils import DataDeletion
        deletion = DataDeletion(
            table=TABLE_NAME,
            conditions=[Condition("StudentID", "=", 99999)]
        )
        deleted_count = self.storage.delete_block(deletion)
        self.assertEqual(deleted_count, 1)
        print(f"    Test record deleted successfully")

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
