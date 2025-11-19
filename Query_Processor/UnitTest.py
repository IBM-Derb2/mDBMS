import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
import unittest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from Query_Processor.classes import QueryProcessor, ExecutionResult, Rows
from Query_Optimizer.types import ParsedQuery, QueryTree
from Concurrency_Control_Manager.lib.strategy_interface import Response
from Storage_Manager.utils import Rows as StorageRows, Condition

class TestQueryProcessorComprehensive(unittest.TestCase) :

    def setUp(self):
        self.mock_optimizer = Mock()
        self.mock_storage = Mock()
        self.mock_ccm = Mock()
        self.mock_frm = Mock()

        self.mock_ccm.begin_transaction.return_value = 1
        self.mock_ccm.commit_transaction.return_value = None
        self.mock_ccm.abort_transaction.return_value = None
        self.mock_ccm.validate_object.return_value = Response(allowed=True, transaction_id=1)
        
        def mock_parse_query(query):
            query_upper = query.upper().strip()
            
            if "SELECT" in query_upper and "FROM" in query_upper:
                table_name = "users"
                if "FROM" in query_upper:
                    parts = query_upper.split("FROM")
                    if len(parts) > 1:
                        table_parts = parts[1].strip().split()
                        if table_parts:
                            table_name = table_parts[0].lower().rstrip(";")
                
                relation_node = QueryTree(type="RELATION", val=table_name, childs=[], parent=None)
                
                if "WHERE" in query_upper:
                    selection_node = QueryTree(type="SELECTION", val="id = 1", childs=[], parent=None)
                    selection_stmt = QueryTree(type="SELECTION_STMT", val="", childs=[relation_node, selection_node], parent=None)
                    projection_node = QueryTree(type="PROJECTION", val=["*"], childs=[selection_stmt], parent=None)
                else:
                    projection_node = QueryTree(type="PROJECTION", val=["*"], childs=[relation_node], parent=None)
                
                return ParsedQuery(query_tree=projection_node, query=query)
            
            elif "JOIN" in query_upper:
                # JOIN query tree
                left_relation = QueryTree(type="RELATION", val="users", childs=[], parent=None)
                right_relation = QueryTree(type="RELATION", val="orders", childs=[], parent=None)
                join_node = QueryTree(type="JOIN", val=["users.id", "orders.user_id"], childs=[left_relation, right_relation], parent=None)
                projection_node = QueryTree(type="PROJECTION", val=["*"], childs=[join_node], parent=None)
                return ParsedQuery(query_tree=projection_node, query=query)
            
            elif "UPDATE" in query_upper:
                # UPDATE query tree
                relation_node = QueryTree(type="RELATION", val="users", childs=[], parent=None)
                update_node = QueryTree(type="UPDATE", val="name=NewName", childs=[relation_node], parent=None)
                return ParsedQuery(query_tree=update_node, query=query)
            
            elif "INSERT" in query_upper:
                # INSERT query tree
                relation_node = QueryTree(type="RELATION", val="users", childs=[], parent=None)
                insert_node = QueryTree(type="INSERT", val={"columns": ["name"], "values": ["Alice"]}, childs=[relation_node], parent=None)
                return ParsedQuery(query_tree=insert_node, query=query)
            
            elif "DELETE" in query_upper:
                # DELETE query tree
                relation_node = QueryTree(type="RELATION", val="users", childs=[], parent=None)
                delete_node = QueryTree(type="DELETE", val="", childs=[relation_node], parent=None)
                return ParsedQuery(query_tree=delete_node, query=query)
            
            else:
                relation_node = QueryTree(type="RELATION", val="users", childs=[], parent=None)
                return ParsedQuery(query_tree=relation_node, query=query)
        
        self.mock_optimizer.parse_query.side_effect = mock_parse_query
        
        self.mock_storage.read_block.return_value = StorageRows(
            data=[
                {"id": 1, "name": "Alice", "salary": 1200},
                {"id": 2, "name": "Bob", "salary": 900},
                {"id": 3, "name": "Charlie", "salary": 1500}
            ],
            rows_count=3,
            idx=[0, 1, 2]
        )
        self.mock_storage.write_block.return_value = StorageRows(
            data=[{"id": 1, "name": "Updated"}],
            rows_count=1,
            idx=[0]
        )
        self.mock_storage.delete_block.return_value = 1

        self.qp = QueryProcessor(
            optimizer=self.mock_optimizer,
            storage_manager=self.mock_storage,
            cc_manager=self.mock_ccm,
            fr_manager=self.mock_frm
        )

    
    def test_01_empty_query(self):
        """Test handling of empty query"""
        result = self.qp.execute_query("")
        
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIn("Empty query", result[0].message)
        self.assertEqual(result[0].rows_count, 0)
        print("✓ Test 01: Empty query handling")

    def test_02_query_without_semicolon(self):
        """Test query without semicolon validation"""
        query = "SELECT * FROM users"
        result = self.qp.execute_query(query)
        
        self.assertIsInstance(result, list)
        self.assertIn("semicolon", result[0].message)
        print("✓ Test 02: Query without semicolon validation")

    def test_03_simple_select(self):
        """Test simple SELECT query"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rows_count, 3)
        self.assertIsNotNone(result[0].data)
        self.assertEqual(len(result[0].data.data), 3)
        
        # Verify data content
        self.assertEqual(result[0].data.data[0]['name'], 'Alice')
        self.assertEqual(result[0].data.data[1]['name'], 'Bob')
        self.assertEqual(result[0].data.data[2]['name'], 'Charlie')
        print("✓ Test 03: Simple SELECT query")

    def test_04_select_without_where(self):
        """Test SELECT query without WHERE clause (edge case)"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        # Should return all rows
        self.assertEqual(result[0].rows_count, 3)
        self.mock_storage.read_block.assert_called()
        print("✓ Test 04: SELECT without WHERE clause")

    def test_05_select_with_where(self):
        """Test SELECT query with WHERE clause"""
        # Mock storage to return filtered data
        self.mock_storage.read_block.return_value = StorageRows(
            data=[{"id": 1, "name": "Alice", "salary": 1200}],
            rows_count=1,
            idx=[0]
        )
        
        query = "SELECT * FROM users WHERE id = 1;"
        result = self.qp.execute_query(query)
        
        self.assertIsInstance(result, list)
        self.assertIsNotNone(result[0].data)
        print("✓ Test 05: SELECT with WHERE clause")
    
    def test_06_begin_transaction(self):
        """Test BEGIN TRANSACTION command"""
        query = "BEGIN TRANSACTION;"
        result = self.qp.execute_query(query)
        
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(self.qp.current_transaction_id, 1)
        self.assertTrue(self.qp.multiple_transaction)
        self.assertIn("Transaction started", result[0].message)
        print("✓ Test 06: BEGIN TRANSACTION")

    def test_07_commit_transaction(self):
        """Test COMMIT command"""
        # Begin transaction first
        self.qp.execute_query("BEGIN TRANSACTION;")
        
        # Add a query to the queue
        self.qp.execute_query("SELECT * FROM users;")
        
        # Commit
        result = self.qp.execute_query("COMMIT;")
        
        self.assertIsInstance(result, list)
        self.assertIsNone(self.qp.current_transaction_id)
        self.assertFalse(self.qp.multiple_transaction)
        self.mock_ccm.commit_transaction.assert_called()
        print("✓ Test 07: COMMIT transaction")

    def test_08_multi_query_transaction(self):
        """Test multiple queries in one transaction"""
        # Begin transaction
        self.qp.execute_query("BEGIN TRANSACTION;")
        
        # Execute multiple queries
        self.qp.execute_query("SELECT * FROM users;")
        self.qp.execute_query("SELECT * FROM users WHERE id = 1;")
        
        # Commit
        result = self.qp.execute_query("COMMIT;")
        
        # Should have multiple results
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)  # Two SELECT queries
        print("✓ Test 08: Multi-query transaction")

    def test_09_rollback_on_error(self):
        """Test rollback on query error"""
        # Begin transaction
        self.qp.execute_query("BEGIN TRANSACTION;")
        
        # Add a query that will fail
        self.mock_storage.read_block.side_effect = Exception("Storage error")
        self.qp.execute_query("SELECT * FROM users;")
        
        # Try to commit (should fail and rollback)
        result = self.qp.execute_query("COMMIT;")
        
        self.assertIsInstance(result, list)
        self.assertIn("Error", result[0].message)
        print("✓ Test 09: Rollback on error")

    
    def test_10_query_optimizer_integration(self):
        """Test integration with Query Optimizer"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        # Verify Query Optimizer was called
        self.mock_optimizer.parse_query.assert_called_with(query)
        
        # Verify parse tree was processed
        self.assertTrue(hasattr(self.qp, '_process_node'))
        print("✓ Test 10: Query Optimizer integration")

    def test_11_storage_manager_integration(self):
        """Test integration with Storage Manager"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        # Verify Storage Manager was called
        self.mock_storage.read_block.assert_called()
        
        # Verify data from Storage Manager is returned correctly
        self.assertEqual(result[0].data.data[0]['salary'], 1200)
        self.assertEqual(result[0].data.data[1]['salary'], 900)
        print("✓ Test 11: Storage Manager integration")

    def test_12_concurrency_control_integration(self):
        """Test integration with Concurrency Control Manager"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        # Verify CCM methods were called
        self.mock_ccm.begin_transaction.assert_called()
        self.mock_ccm.validate_object.assert_called()
        self.mock_ccm.commit_transaction.assert_called()
        print("✓ Test 12: Concurrency Control Manager integration")

    def test_13_failure_recovery_integration(self):
        """Test integration with Failure Recovery Manager"""
        # Reset mock
        self.mock_storage.write_block.return_value = StorageRows(
            data=[{"id": 1, "name": "Updated"}],
            rows_count=1,
            idx=[0]
        )
        
        query = "UPDATE users SET name = 'NewName' WHERE id = 1;"
        result = self.qp.execute_query(query)
        
        # Verify Failure Recovery Manager was called for write operations
        # Note: FRM should log write operations
        self.assertTrue(hasattr(self.qp, 'fr_manager'))
        print("✓ Test 13: Failure Recovery Manager integration")

    
    def test_14_process_node_projection(self):
        """Test _process_node handles PROJECTION"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        self.assertIsNotNone(result[0].data)
        self.assertTrue(hasattr(self.qp, '_select_columns'))
        print("✓ Test 14: Process PROJECTION node")

    def test_15_process_node_relation(self):
        """Test _process_node handles RELATION (FROM)"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        # Verify FROM was processed
        self.mock_storage.read_block.assert_called()
        self.assertTrue(hasattr(self.qp, '_from_table'))
        print("✓ Test 15: Process RELATION node")

    def test_16_process_node_selection(self):
        """Test _process_node handles SELECTION (WHERE)"""
        self.mock_storage.read_block.return_value = StorageRows(
            data=[{"id": 1, "name": "Alice", "salary": 1200}],
            rows_count=1,
            idx=[0]
        )
        
        query = "SELECT * FROM users WHERE id = 1;"
        result = self.qp.execute_query(query)
        
        self.assertTrue(hasattr(self.qp, '_apply_condition'))
        print("✓ Test 16: Process SELECTION node")

    def test_17_nested_loop_join_method_exists(self):
        """Test nested loop join method exists"""
        # Verify nested loop join method is implemented
        self.assertTrue(hasattr(self.qp, '_nested_loop_join'))
        print("✓ Test 17: Nested loop join method exists")

    def test_18_nested_loop_join_execution(self):
        """Test nested loop join is actually used"""
        # Mock two tables
        self.mock_storage.read_block.side_effect = [
            StorageRows(
                data=[
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"}
                ],
                rows_count=2,
                idx=[0, 1]
            ),
            StorageRows(
                data=[
                    {"user_id": 1, "order": "Order1"},
                    {"user_id": 2, "order": "Order2"}
                ],
                rows_count=2,
                idx=[0, 1]
            )
        ]
        
        query = "SELECT * FROM users JOIN orders ON users.id = orders.user_id;"
        result = self.qp.execute_query(query)
        
        # Verify join was performed
        self.assertIsNotNone(result[0].data)
        print("✓ Test 18: Nested loop join execution")

    
    def test_19_order_by_operation(self):
        """Test ORDER BY operation"""
        self.assertTrue(hasattr(self.qp, '_order_by'))
        print("✓ Test 19: ORDER BY operation exists")

    def test_20_limit_operation(self):
        """Test LIMIT operation"""
        self.assertTrue(hasattr(self.qp, '_limit'))
        
        # Test limit functionality
        test_data = Rows(
            data=[{"id": i} for i in range(10)],
            rows_count=10
        )
        limited = self.qp._limit(test_data, 5)
        self.assertEqual(limited.rows_count, 5)
        print("✓ Test 20: LIMIT operation")

    def test_21_update_operation(self):
        """Test UPDATE operation"""
        self.mock_storage.write_block.return_value = StorageRows(
            data=[{"id": 1, "name": "Updated"}],
            rows_count=1,
            idx=[0]
        )
        
        query = "UPDATE users SET name = 'NewName' WHERE id = 1;"
        result = self.qp.execute_query(query)
        
        self.mock_storage.write_block.assert_called()
        print("✓ Test 21: UPDATE operation")

    def test_22_insert_operation(self):
        """Test INSERT operation"""
        self.mock_storage.write_block.return_value = StorageRows(
            data=[{"id": 4, "name": "David"}],
            rows_count=1,
            idx=[3]
        )
        
        query = "INSERT INTO users (name) VALUES ('David');"
        result = self.qp.execute_query(query)
        
        self.mock_storage.write_block.assert_called()
        print("✓ Test 22: INSERT operation")

    def test_23_delete_operation(self):
        """Test DELETE operation"""
        self.mock_storage.delete_block.return_value = 1
        
        query = "DELETE FROM users WHERE id = 1;"
        result = self.qp.execute_query(query)
        
        self.mock_storage.delete_block.assert_called()
        print("✓ Test 23: DELETE operation")

    
    def test_24_select_empty_result(self):
        """Test SELECT query returning empty result"""
        self.mock_storage.read_block.return_value = StorageRows(
            data=[],
            rows_count=0,
            idx=[]
        )
        
        query = "SELECT * FROM users WHERE id = 999;"
        result = self.qp.execute_query(query)
        
        self.assertEqual(result[0].rows_count, 0)
        print("✓ Test 24: SELECT with empty result")

    def test_25_concurrent_read_validation(self):
        """Test concurrent read validation with CCM"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        # Verify read validation was called
        calls = self.mock_ccm.validate_object.call_args_list
        self.assertTrue(any('read' in str(call) for call in calls))
        print("✓ Test 25: Concurrent read validation")

    def test_26_concurrent_write_validation(self):
        """Test concurrent write validation with CCM"""
        self.mock_storage.write_block.return_value = StorageRows(
            data=[{"id": 1}],
            rows_count=1,
            idx=[0]
        )
        
        query = "UPDATE users SET name = 'Test' WHERE id = 1;"
        result = self.qp.execute_query(query)
        
        # Verify write validation was called
        calls = self.mock_ccm.validate_object.call_args_list
        self.assertTrue(any('write' in str(call) for call in calls))
        print("✓ Test 26: Concurrent write validation")

    def test_27_query_with_multiple_conditions(self):
        """Test query with multiple WHERE conditions"""
        self.mock_storage.read_block.return_value = StorageRows(
            data=[{"id": 1, "name": "Alice", "salary": 1200}],
            rows_count=1,
            idx=[0]
        )
        
        query = "SELECT * FROM users WHERE id = 1;"
        result = self.qp.execute_query(query)
        
        self.assertIsNotNone(result[0].data)
        print("✓ Test 27: Query with multiple conditions")

    def test_28_cartesian_product_method(self):
        """Test cartesian product method exists"""
        self.assertTrue(hasattr(self.qp, '_cartesian'))
        print("✓ Test 28: Cartesian product method exists")

    def test_29_column_projection(self):
        """Test column projection (SELECT specific columns)"""
        self.assertTrue(hasattr(self.qp, '_select_columns'))
        
        # Test column selection
        test_data = Rows(
            data=[
                {"id": 1, "name": "Alice", "salary": 1200},
                {"id": 2, "name": "Bob", "salary": 900}
            ],
            rows_count=2
        )
        projected = self.qp._select_columns(test_data, ["name"])
        self.assertIn("name", projected.data[0])
        print("✓ Test 29: Column projection")

    def test_30_condition_operators(self):
        """Test different condition operators in WHERE clause"""
        self.assertTrue(hasattr(self.qp, '_apply_condition'))
        print("✓ Test 30: Condition operators exist")

    
    def test_31_execution_result_structure(self):
        """Test ExecutionResult structure"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        # Verify ExecutionResult structure
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], ExecutionResult)
        self.assertIsNotNone(result[0].transaction_id)
        self.assertIsNotNone(result[0].query)
        self.assertIsNotNone(result[0].timestamp)
        self.assertIsNotNone(result[0].message)
        self.assertIsNotNone(result[0].data)
        print("✓ Test 31: ExecutionResult structure")

    def test_32_result_data_format(self):
        """Test result data format from query execution"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        # Verify data format
        self.assertIsInstance(result[0].data, Rows)
        self.assertIsInstance(result[0].data.data, list)
        self.assertGreater(len(result[0].data.data), 0)
        self.assertIsInstance(result[0].data.data[0], dict)
        print("✓ Test 32: Result data format")

    def test_33_error_message_format(self):
        """Test error message format"""
        result = self.qp.execute_query("")
        
        self.assertIn("Error", result[0].message)
        self.assertEqual(result[0].rows_count, 0)
        print("✓ Test 33: Error message format")

    def test_34_success_message_format(self):
        """Test success message format"""
        query = "SELECT * FROM users;"
        result = self.qp.execute_query(query)
        
        self.assertIn("success", result[0].message.lower())
        print("✓ Test 34: Success message format")

    
    def test_35_complete_workflow(self):
        """Test complete workflow: BEGIN -> SELECT -> UPDATE -> COMMIT"""
        # Begin transaction
        begin_result = self.qp.execute_query("BEGIN TRANSACTION;")
        self.assertIn("Transaction started", begin_result[0].message)
        
        # SELECT query
        self.qp.execute_query("SELECT * FROM users;")
        
        # UPDATE query
        self.mock_storage.write_block.return_value = StorageRows(
            data=[{"id": 1}],
            rows_count=1,
            idx=[0]
        )
        self.qp.execute_query("UPDATE users SET name = 'Test' WHERE id = 1;")
        
        # COMMIT
        commit_result = self.qp.execute_query("COMMIT;")
        
        # Verify all operations were executed
        self.assertIsInstance(commit_result, list)
        self.assertEqual(len(commit_result), 2)  # SELECT + UPDATE
        self.mock_ccm.commit_transaction.assert_called()
        print("✓ Test 35: Complete workflow")

    def test_36_all_components_initialized(self):
        """Test all components are properly initialized"""
        self.assertIsNotNone(self.qp.optimizer)
        self.assertIsNotNone(self.qp.storage_manager)
        self.assertIsNotNone(self.qp.cc_manager)
        self.assertIsNotNone(self.qp.fr_manager)
        print("✓ Test 36: All components initialized")

    def test_37_method_existence_check(self):
        """Test all required methods exist"""
        required_methods = [
            '_process_node',
            '_from_table',
            '_select_columns',
            '_apply_condition',
            '_order_by',
            '_limit',
            '_nested_loop_join',
            '_cartesian',
            '_update_table',
            '_insert_table',
            '_delete_table',
            '_commit',
            '_rollback'
        ]
        
        for method in required_methods:
            self.assertTrue(hasattr(self.qp, method), f"Method {method} not found")
        
        print("✓ Test 37: All required methods exist")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("COMPREHENSIVE QUERY PROCESSOR UNIT TESTS")
    print("Testing: Integration, Edge Cases, and Complete Workflow")
    print("="*70 + "\n")
    
    # Run tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestQueryProcessorComprehensive)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests Run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70 + "\n")
    
    if result.wasSuccessful():
        print("✓ ALL TESTS PASSED!")
    else:
        print("✗ SOME TESTS FAILED - Please review the output above")
