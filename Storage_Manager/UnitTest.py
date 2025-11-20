import unittest
import time
import os
import random

from storage_engine import StorageEngine
from utils import DataRetrieval, Condition
from serializer import Serializer


class TestStorageEngine(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        print("\nSetup: Generating test data")

        random.seed(2025)
        cls.serializer = Serializer()
        cls.storage = StorageEngine(serializer=cls.serializer)

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

    def test_get_stats(self):
        stats = self.storage.get_stats("student")

        self.assertIsNotNone(stats)
        print(f"Test get_stats:\n{stats}")

    def test_index_performance(self):
        TABLE_NAME = "student"
        COLUMN_NAME = "GPA"
        TARGET_VALUE = 4.0
        ITERATIONS = 100

        condition = [Condition(column=COLUMN_NAME, operation="=", operand=TARGET_VALUE)]

        print(f"\nTest index_performance:\nStarting benchmark ({ITERATIONS} iterations)")

        idx_file = f"data/{TABLE_NAME}_{COLUMN_NAME}_hash.dat"
        if os.path.exists(idx_file):
            os.remove(idx_file)

        start_idx = time.perf_counter()
        self.storage.set_index(TABLE_NAME, COLUMN_NAME, "hash")
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

    def test_read_block(self):
        dr = DataRetrieval(
            table="student",
            column=["StudentID", "FullName", "GPA"],
            conditions=[Condition("GPA", ">", 3.5)]
        )
        rows = self.storage.read_block(dr)

        self.assertGreater(rows.rows_count, 0)
        print(f"Test read_block:\n{rows.rows_count} rows found (GPA > 3.5)")
        
if __name__ == "__main__":
    unittest.main(verbosity=0)
