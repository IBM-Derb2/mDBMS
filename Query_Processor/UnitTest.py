import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
import unittest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from Query_Processor.classes import QueryProcessor, ExecutionResult, Rows

from Query_Optimizer.classes import ParsedQuery
from Concurrency_Control_Manager.classes import Response
from Storage_Manager.classes import Rows as StorageRows

class TestQueryProcessor(unittest.TestCase):

    def setUp(self):
        
        self.mock_optimizer = Mock()
        self.mock_storage = Mock()
        self.mock_ccm = Mock()
        self.mock_frm = Mock()

        self.mock_ccm.begin_transaction.return_value = 1
        self.mock_ccm.validate_object.return_value = Response(allowed=True, transaction_id=1)
        
        self.mock_optimizer.parse_query.return_value = ParsedQuery(
            query_str="SELECT *", plan_details="Mocked Plan"
        )
        self.mock_optimizer.optimize_query.return_value = ParsedQuery(
            query_str="SELECT *", plan_details="Optimized Mocked Plan"
        )
        
        self.mock_storage.read_block.return_value = StorageRows(
            data=[{"id": 1, "name": "Test"}]
        )
        self.mock_storage.write_block.return_value = 1 # 1 row affected
        self.mock_storage.delete_block.return_value = 1 # 1 row affected

        self.qp = QueryProcessor(
            optimizer=self.mock_optimizer,
            storage_manager=self.mock_storage,
            cc_manager=self.mock_ccm,
            fr_manager=self.mock_frm
        )

    def test_01_execute_begin_transaction(self):
        query = "BEGIN TRANSACTION"
        result = self.qp.execute_query(query)
        
        self.mock_ccm.begin_transaction.assert_called_once()
        self.assertEqual(self.qp.current_transaction_id, 1)
        self.assertIn("Transaction started", result.message)

    def test_02_execute_commit(self):
        self.qp.execute_query("BEGIN TRANSACTION")
        
        query = "COMMIT"
        result = self.qp.execute_query(query)

        self.mock_ccm.end_transaction.assert_called_with(1)
        self.mock_frm.write_log.assert_called_with(result)
        self.assertIsNone(self.qp.current_transaction_id)
        self.assertIn("Transaction committed", result.message)

    def test_03_execute_select(self):
        query = "SELECT * FROM users"
        result = self.qp.execute_query(query)

        self.mock_optimizer.parse_query.assert_called_with(query)
        self.mock_optimizer.optimize_query.assert_called()
        self.mock_ccm.validate_object.assert_called_with(
            unittest.mock.ANY, 1, "read"
        )
        self.mock_storage.read_block.assert_called()
        self.mock_frm.write_log.assert_called_with(result)
        
        self.assertEqual(result.rows_count, 1)
        self.assertEqual(result.data.data[0]['name'], 'Test')

    def test_04_execute_update_bonus(self):
        query = "UPDATE users SET name = 'New' WHERE id = 1"
        result = self.qp.execute_query(query)

        self.mock_ccm.validate_object.assert_called_with(
            unittest.mock.ANY, 1, "write"
        )
        self.mock_storage.write_block.assert_called()
        self.mock_frm.write_log.assert_called_with(result)
        
        self.assertEqual(result.rows_count, 1)
        self.assertIn("UPDATE executed", result.message)

    def test_05_execute_delete_bonus(self):
        query = "DELETE FROM users WHERE id = 1"
        result = self.qp.execute_query(query)

        self.mock_ccm.validate_object.assert_called_with(
            unittest.mock.ANY, 1, "write"
        )
        self.mock_storage.delete_block.assert_called()
        self.mock_frm.write_log.assert_called_with(result)

        self.assertEqual(result.rows_count, 1)
        self.assertIn("DELETE executed", result.message)

    def test_06_execute_rollback(self):
        self.qp.execute_query("BEGIN TRANSACTION")
        
        query = "ROLLBACK"
        result = self.qp.execute_query(query)

        self.mock_ccm.end_transaction.assert_called_with(1)
        self.mock_frm.write_log.assert_called_with(result)
        self.assertIsNone(self.qp.current_transaction_id)
        self.assertIn("rolled back", result.message)

    def test_07_error_handling_rollback(self):
        self.mock_storage.read_block.side_effect = Exception("Storage error")
        
        query = "SELECT * FROM users"
        result = self.qp.execute_query(query)

        self.assertIn("Error", result.message)
        self.assertIsNone(self.qp.current_transaction_id)

    def test_08_empty_query_validation(self):
        result = self.qp.execute_query("")
        
        self.assertIn("Empty query", result.message)
        self.assertEqual(result.rows_count, 0)

    def test_09_insert_bonus(self):
        query = "INSERT INTO users (name) VALUES ('Alice')"
        result = self.qp.execute_query(query)

        self.mock_storage.write_block.assert_called()
        self.mock_frm.write_log.assert_called_with(result)
        self.assertIn("INSERT executed", result.message)

    def test_10_create_table_bonus(self):
        query = "CREATE TABLE users (id INT, name VARCHAR)"
        result = self.qp.execute_query(query)

        self.mock_storage.write_block.assert_called()
        self.mock_frm.write_log.assert_called_with(result)
        self.assertIn("CREATE TABLE executed", result.message)

    def test_11_drop_table_bonus(self):
        query = "DROP TABLE users"
        result = self.qp.execute_query(query)

        self.mock_storage.delete_block.assert_called()
        self.mock_frm.write_log.assert_called_with(result)
        self.assertIn("DROP TABLE executed", result.message)

    def test_12_table_name_extraction(self):
        test_cases = [
            ("SELECT * FROM users", "users"),
            ("UPDATE employees SET name = 'X'", "employees"),
            ("DELETE FROM products WHERE id = 1", "products"),
            ("INSERT INTO orders (id) VALUES (1)", "orders"),
        ]
        
        for query, expected_table in test_cases:
            table_name = self.qp._extract_table_name(query)
            self.assertEqual(table_name, expected_table, f"Failed for query: {query}")

    def test_13_commit_without_transaction(self):
        result = self.qp.execute_query("COMMIT")
        
        self.assertIn("Error", result.message)
        self.assertIn("No active transaction", result.message)

    def test_14_rollback_without_transaction(self):
        result = self.qp.execute_query("ROLLBACK")
        
        self.assertIn("Error", result.message)
        self.assertIn("No active transaction", result.message)

if __name__ == "__main__":
    unittest.main()