import sys
import os
import unittest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Query_Processor.classes import QueryProcessor
from Concurrency_Control_Manager.classes import ConcurrencyControlManager
from Storage_Manager.storage_engine import StorageEngine
from Storage_Manager.serializer import Serializer
from Query_Optimizer.optimization_engine import OptimizationEngine
from Failure_Recovery.buffer_manager import BufferManager
from Failure_Recovery.failure_recovery_manager import FailureRecoveryManager

class TestQueryProcessor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.optimizer_engine = OptimizationEngine()
        cls.serializer = Serializer()
        cls.storage_engine = StorageEngine(serializer=cls.serializer)
        
        cls.buffer_manager = BufferManager(capacity=100)
        cls.frm = FailureRecoveryManager(
            buffer_manager=cls.buffer_manager,
            load_table_callback=cls.storage_engine.read_disk_to_buffer,
            save_buffer_callback=cls.storage_engine.save_buffer_to_disk,
            log_directory="logs",
            checkpoint_interval=10
        )
        
        cls.storage_engine.frm = cls.frm
        cls.ccm = ConcurrencyControlManager(frm=cls.frm)
        cls.storage_engine.cc_manager = cls.ccm

    def setUp(self):
        self.qp = QueryProcessor(
            optimizer=self.optimizer_engine,
            storage_manager=self.storage_engine,
            cc_manager=self.ccm,
            fr_manager=self.frm
        )

    def test_01_empty_query(self):
        """Test handling of empty query"""

        result = self.qp.execute_query("")
        self.assertEqual(len(result), 1)
        self.assertIn("Empty query", result[0].message)
        self.assertEqual(result[0].rows_count, 0)

    def test_02_query_without_semicolon(self):
        """Test query without semicolon validation"""

        query = "SELECT * FROM student"
        result = self.qp.execute_query(query)
        self.assertIn("semicolon", result[0].message)

    def test_03_simple_select(self):
        """Test simple SELECT query"""

        query = "SELECT * FROM student;"
        result = self.qp.execute_query(query)
        self.assertEqual(len(result), 1)
        self.assertGreater(result[0].rows_count, 0)
        self.assertIsNotNone(result[0].data)

    def test_04_select_with_columns_and_limit(self):
        """Test SELECT with specific columns and LIMIT"""

        query = "SELECT StudentID, FullName FROM student LIMIT 1;"
        result = self.qp.execute_query(query)
        self.assertEqual(result[0].rows_count, 1)
        row = result[0].data.data[0]
        self.assertIn("studentid", row)
        self.assertIn("fullname", row)

    def test_05_select_with_where(self):
        """Test SELECT with WHERE clause"""

        query = "SELECT * FROM student WHERE StudentID = 1;"
        result = self.qp.execute_query(query)
        if result[0].rows_count > 0:

            self.assertEqual(result[0].data.data[0]["studentid"], 1)

    def test_06_select_empty_result(self):
        """Test SELECT returning empty result"""

        query = "SELECT * FROM student WHERE StudentID = 999999;"
        result = self.qp.execute_query(query)
        self.assertEqual(result[0].rows_count, 0)

    def test_07_begin_transaction(self):
        """Test BEGIN TRANSACTION command"""

        query = "BEGIN TRANSACTION;"
        result = self.qp.execute_query(query)
        self.assertEqual(len(result), 1)
        self.assertIsNotNone(self.qp.current_transaction_id)
        self.assertTrue(len(str(self.qp.current_transaction_id)) > 0)
        self.assertTrue(self.qp.multiple_transaction)
        self.assertIn("Transaction started", result[0].message)

    def test_08_transaction_workflow(self):
        """Test transaction workflow: BEGIN -> SELECT -> COMMIT"""

        self.qp.execute_query("BEGIN TRANSACTION;")
        self.qp.execute_query("SELECT * FROM student;")
        result = self.qp.execute_query("COMMIT;")
        self.assertIsNone(self.qp.current_transaction_id)
        self.assertFalse(self.qp.multiple_transaction)

    def test_09_multi_query_transaction(self):
        """Test multiple queries in one transaction"""

        self.qp.execute_query("BEGIN TRANSACTION;")
        result1 = self.qp.execute_query("SELECT * FROM student;")
        result2 = self.qp.execute_query("SELECT * FROM course;")
        result = self.qp.execute_query("COMMIT;")
        # COMMIT returns accumulated results from the transaction
        self.assertGreaterEqual(len(result), 1)
        self.assertGreater(result1[0].rows_count, 0)
        self.assertGreater(result2[0].rows_count, 0)

    def test_10_select_with_where_multiple_rows(self):
        """Test SELECT returning multiple rows"""

        query = "SELECT * FROM student WHERE GPA > 3.0;"
        result = self.qp.execute_query(query)
        self.assertGreater(result[0].rows_count, 0)

    def test_11_select_with_order_by(self):
        """Test SELECT with ORDER BY"""

        query = "SELECT * FROM student ORDER BY StudentID ASC;"
        result = self.qp.execute_query(query)
        self.assertGreater(result[0].rows_count, 0)
        if result[0].rows_count > 1:

            ids = [row.get("studentid") for row in result[0].data.data]
            self.assertEqual(ids, sorted(ids))

    def test_12_select_with_limit(self):
        """Test SELECT with LIMIT"""

        query = "SELECT * FROM student LIMIT 5;"
        result = self.qp.execute_query(query)
        self.assertEqual(result[0].rows_count, 5)

    def test_13_theta_join(self):
        """Test THETA JOIN with condition"""

        query = "SELECT * FROM student JOIN attends ON student.StudentID = attends.StudentID;"
        result = self.qp.execute_query(query)
        if result[0].rows_count > 0:
            row = result[0].data.data[0]

            self.assertIn("student.studentid", row)
            self.assertIn("attends.courseid", row)

    def test_14_cross_join_cartesian_product(self):
        """Test CROSS JOIN (cartesian product)"""

        query = "SELECT * FROM student, attends LIMIT 10;"
        result = self.qp.execute_query(query)
        self.assertGreater(result[0].rows_count, 0)
        row = result[0].data.data[0]

        has_student_id = any("studentid" in k for k in row.keys())
        has_course_id = any("courseid" in k for k in row.keys())
        self.assertTrue(has_student_id)
        self.assertTrue(has_course_id)

    def test_15_execution_result_structure(self):
        """Test ExecutionResult structure"""
        
        query = "SELECT * FROM student LIMIT 1;"
        result = self.qp.execute_query(query)
        self.assertIsNotNone(result[0].transaction_id)
        self.assertIsNotNone(result[0].query)
        self.assertIsNotNone(result[0].timestamp)
        self.assertIsNotNone(result[0].message)

    def test_16_result_data_format(self):
        """Test result data format"""

        query = "SELECT * FROM student LIMIT 1;"
        result = self.qp.execute_query(query)
        self.assertEqual(len(result[0].data.data), 1)

    def test_17_components_initialized(self):
        """Test all components are properly initialized"""

        self.assertIsNotNone(self.qp.optimizer)
        self.assertIsNotNone(self.qp.storage_manager)
        self.assertIsNotNone(self.qp.cc_manager)
        self.assertIsNotNone(self.qp.fr_manager)

    def test_18_join_data_integrity(self):
        """Test JOIN produces correct data"""

        query = "SELECT * FROM student JOIN attends ON student.StudentID = attends.StudentID LIMIT 1;"
        result = self.qp.execute_query(query)
        if result[0].rows_count > 0:
            row = result[0].data.data[0]

            student_id = row.get("student.studentid")
            self.assertIsNotNone(student_id)

    def test_19_transaction_isolation(self):
        """Test transaction state isolation"""

        self.qp.execute_query("BEGIN TRANSACTION;")
        initial_tid = self.qp.current_transaction_id
        self.assertIsNotNone(initial_tid)
        self.qp.execute_query("COMMIT;")
        self.assertIsNone(self.qp.current_transaction_id)

    def test_20_transaction_rollback(self):
        """Test ROLLBACK command aborts transaction"""

        self.qp.execute_query("BEGIN TRANSACTION;")
        tid = self.qp.current_transaction_id
        self.assertIsNotNone(tid)
        self.qp.execute_query("ROLLBACK;")
        self.assertIsNone(self.qp.current_transaction_id)
        self.assertFalse(self.qp.multiple_transaction)

    def test_21_error_handling(self):
        """Test error handling for invalid query"""
        
        query = "INVALID QUERY;"
        result = self.qp.execute_query(query)
        self.assertGreater(len(result[0].message), 0)
        self.assertTrue(any(word in result[0].message.lower() for word in ['error', 'invalid', 'unhandled']))

    def test_24_delete_rows(self):
        """Test DELETE data removal using record from test_22"""

        unique_id = 69420

        delete_query = f"DELETE FROM student WHERE StudentID = {unique_id};"
        self.qp.execute_query(delete_query)

        verify_query = f"SELECT * FROM student WHERE StudentID = {unique_id};"
        select_result = self.qp.execute_query(verify_query)
        self.assertEqual(select_result[0].rows_count, 0)

    def test_25_create_drop_table(self):
        """Test CREATE TABLE and DROP TABLE operations"""

        table_name = "test_temp_table"
        
        # Clean up table if it exists from previous run
        self.qp.execute_query(f"DROP TABLE {table_name};")

        create_query = f"CREATE TABLE {table_name} (id int, name char(50), score float);"
        result = self.qp.execute_query(create_query)
        self.assertIn("created successfully", result[0].message.lower())

        insert_query = f"INSERT INTO {table_name} (id, name, score) VALUES (1, 'Test', 95.5);"
        insert_result = self.qp.execute_query(insert_query)
        self.assertEqual(insert_result[0].rows_count, 1)

        select_query = f"SELECT * FROM {table_name};"
        select_result = self.qp.execute_query(select_query)
        self.assertEqual(select_result[0].rows_count, 1)
        if select_result[0].rows_count > 0:
            self.assertEqual(select_result[0].data.data[0]["id"], 1)

        drop_query = f"DROP TABLE {table_name};"
        drop_result = self.qp.execute_query(drop_query)
        self.assertIn("dropped successfully", drop_result[0].message.lower())

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestQueryProcessor)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print(f"\nTests Run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}\n")

    if not result.wasSuccessful():
        print("SOME TESTS FAILED")
