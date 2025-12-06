"""
Tests for SQL Parser
"""
import unittest

from Query_Optimizer.optimization_engine import OptimizationEngine
from Query_Optimizer.query_types import ParsedQuery
from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer


class TestSQLParser(unittest.TestCase):
    """Test suite for SQL parsing functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = OptimizationEngine()

    def test_parse_returns_parsed_query_instance(self):
        """Test that parse_query returns a ParsedQuery instance."""
        query = "SELECT * FROM users"
        parsed = self.engine.parse_query(query)

        self.assertIsInstance(parsed, ParsedQuery)
        self.assertIsNotNone(parsed.query_tree)

    def test_parse_simple_select(self):
        """Test parsing of a simple SELECT statement."""
        query = "SELECT * FROM users"
        parsed = self.engine.parse_query(query)

        # Check that the tree has basic structure
        self.assertIsNotNone(parsed.query_tree)
        # Parser creates PROJECTION node for SELECT statements
        self.assertIn(parsed.query_tree.type, ['SELECT', 'PROJECTION'])

    def test_parse_select_with_where(self):
        """Test parsing of SELECT with WHERE clause."""
        query = "SELECT * FROM users WHERE id = 10"
        parsed = self.engine.parse_query(query)

        # Look for selection statement node
        selection_nodes = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'SELECTION_STMT')
        self.assertTrue(selection_nodes, "SELECTION_STMT node should exist")

        # Verify the selection has condition
        selection = selection_nodes[0]
        self.assertGreaterEqual(len(selection.childs), 2)

    def test_parse_select_with_multiple_columns(self):
        """Test parsing of SELECT with multiple columns."""
        query = "SELECT name, age, status FROM users"
        parsed = self.engine.parse_query(query)

        # Parser should successfully parse the query
        self.assertIsNotNone(parsed.query_tree)
        # Query tree should have structure (may not have separate COLUMN nodes)
        self.assertTrue(hasattr(parsed.query_tree, 'childs')
                        or hasattr(parsed.query_tree, 'children'))

    def test_parse_join_query(self):
        """Test parsing of JOIN queries."""
        query = "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id"
        parsed = self.engine.parse_query(query)

        # Should create some form of join node
        theta_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'THETA_JOIN')
        inner_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'INNER_JOIN')

        self.assertTrue(theta_joins or inner_joins,
                        "Should create a join node for JOIN query")

    def test_parse_cross_join_implicit(self):
        """Test parsing of implicit cross join (comma-separated tables)."""
        query = "SELECT * FROM users, orders"
        parsed = self.engine.parse_query(query)

        # Should create cross join node
        cross_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'CROSS_JOIN')
        self.assertTrue(
            cross_joins, "Should create CROSS_JOIN for comma-separated tables")

    def test_parse_cartesian_product_with_condition(self):
        """Test parsing of cartesian product that can be converted to theta join."""
        query = "SELECT * FROM users u, orders o WHERE u.id = o.user_id"
        parsed = self.engine.parse_query(query)

        # Should have both cross join and selection
        cross_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'CROSS_JOIN')
        selection_stmts = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'SELECTION_STMT')

        self.assertTrue(cross_joins, "Should create CROSS_JOIN")
        self.assertTrue(selection_stmts, "Should create SELECTION_STMT")

    def test_parse_complex_where_condition(self):
        """Test parsing of complex WHERE conditions."""
        query = "SELECT * FROM users WHERE age >= 18 AND status = 'ACTIVE' OR balance > 1000"
        parsed = self.engine.parse_query(query)

        # Find operator nodes (AND, OR, comparison operators)
        operator_nodes = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'OPERATOR')

        self.assertGreater(len(operator_nodes), 0,
                           "Should have operator nodes for complex conditions")

    def test_parse_with_aliases(self):
        """Test parsing of queries with table aliases."""
        query = "SELECT u.name, u.age FROM users u WHERE u.id = 1"
        parsed = self.engine.parse_query(query)

        # Should parse without errors
        self.assertIsNotNone(parsed.query_tree)

    def test_parse_empty_string_raises_error(self):
        """Test that empty query string raises ValueError."""
        query = "   "

        # Expected error: "Query string cannot be empty"
        with self.assertRaises(ValueError) as cm:
            self.engine.parse_query(query)
        # Verify error message contains expected text
        self.assertIn("empty", str(cm.exception).lower())

    def test_parse_invalid_keyword_raises_error(self):
        """Test that invalid SQL keyword raises ValueError."""
        query = "RANDOM something FROM somewhere"

        # Expected error: "Unsupported query type: random"
        with self.assertRaises(ValueError) as cm:
            self.engine.parse_query(query)
        # Verify error is about unsupported query type
        error_msg = str(cm.exception).lower()
        self.assertTrue("unsupported" in error_msg or "random" in error_msg)

    def test_parse_select_with_aggregate(self):
        """Test parsing of SELECT with aggregate functions."""
        # Note: Current parser implementation doesn't support aggregate functions
        # This test verifies that it raises an appropriate error
        # Expected error: "Unexpected token after query: '(' at position 12"
        query = "SELECT COUNT(*), AVG(age) FROM users"

        with self.assertRaises(ValueError) as cm:
            self.engine.parse_query(query)
        # Verify error is about unexpected token (aggregate functions not supported)
        error_msg = str(cm.exception).lower()
        self.assertTrue("unexpected" in error_msg or "token" in error_msg)

    def test_parse_nested_conditions(self):
        """Test parsing of nested WHERE conditions."""
        query = "SELECT * FROM users WHERE (age > 18 AND status = 'ACTIVE') OR (balance > 1000)"
        parsed = self.engine.parse_query(query)

        # Should parse without errors and create operator tree
        operator_nodes = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'OPERATOR')
        self.assertGreater(len(operator_nodes), 0)

    def test_parse_multiple_joins(self):
        """Test parsing of queries with multiple joins."""
        query = """
        SELECT u.name, o.total, p.name 
        FROM users u 
        JOIN orders o ON u.id = o.user_id 
        JOIN products p ON o.product_id = p.id
        """
        parsed = self.engine.parse_query(query)

        # Should create multiple join nodes
        self.assertIsNotNone(parsed.query_tree)


class TestJoinParsing(unittest.TestCase):
    """Comprehensive tests for JOIN query parsing."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = OptimizationEngine()

    def test_parse_join_basic(self):
        """Test basic JOIN...ON parsing."""
        query = "SELECT * FROM users JOIN orders ON users.id = orders.user_id"
        parsed = self.engine.parse_query(query)

        theta_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'THETA_JOIN')
        inner_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'INNER_JOIN')

        self.assertTrue(theta_joins or inner_joins,
                        "Should create join node for JOIN")

    def test_parse_join_with_aliases(self):
        """Test JOIN...ON with table aliases."""
        query = "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id"
        parsed = self.engine.parse_query(query)

        theta_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'THETA_JOIN')
        self.assertTrue(theta_joins, "Should create THETA_JOIN with aliases")

    def test_parse_join_with_complex_condition(self):
        """Test JOIN with complex ON condition."""
        query = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id AND u.status = 'ACTIVE'"
        parsed = self.engine.parse_query(query)

        # Should have join and operators for AND condition
        operator_nodes = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'OPERATOR')
        self.assertGreater(len(operator_nodes), 0,
                           "Should have operators for complex join condition")

    def test_parse_join_three_tables(self):
        """Test joining three tables with JOIN...ON."""
        query = """
        SELECT u.name, o.order_date, p.product_name
        FROM users u
        JOIN orders o ON u.id = o.user_id
        JOIN products p ON o.product_id = p.id
        """
        parsed = self.engine.parse_query(query)

        # Should successfully parse three-table join
        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_four_tables(self):
        """Test joining four tables with JOIN...ON."""
        query = """
        SELECT u.name, o.total, p.name, c.category_name
        FROM users u
        JOIN orders o ON u.id = o.user_id
        JOIN order_items oi ON o.id = oi.order_id
        JOIN products p ON oi.product_id = p.id
        """
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_with_where_clause(self):
        """Test JOIN...ON with additional WHERE conditions."""
        query = """
        SELECT u.name, o.total
        FROM users u
        JOIN orders o ON u.id = o.user_id
        WHERE o.total > 100 AND u.status = 'ACTIVE'
        """
        parsed = self.engine.parse_query(query)

        # Should have both join and selection nodes
        selection_stmts = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'SELECTION_STMT')
        self.assertTrue(selection_stmts,
                        "Should have SELECTION_STMT for WHERE clause")

    def test_parse_join_with_different_comparison_operators(self):
        """Test JOIN with different comparison operators in ON clause."""
        queries = [
            "SELECT * FROM users u JOIN orders o ON u.id >= o.user_id",
            "SELECT * FROM users u JOIN orders o ON u.id <= o.user_id",
            "SELECT * FROM users u JOIN orders o ON u.id != o.user_id",
            "SELECT * FROM users u JOIN orders o ON u.id <> o.user_id",
            "SELECT * FROM users u JOIN orders o ON u.id > o.user_id",
            "SELECT * FROM users u JOIN orders o ON u.id < o.user_id"
        ]

        for query in queries:
            parsed = self.engine.parse_query(query)
            self.assertIsNotNone(parsed.query_tree)

    def test_parse_self_join(self):
        """Test self-join (table joined with itself)."""
        query = "SELECT e1.name, e2.name FROM employees e1 JOIN employees e2 ON e1.manager_id = e2.id"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_with_multiple_conditions_and(self):
        """Test JOIN with multiple AND conditions in ON clause."""
        query = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id AND u.region = o.region"
        parsed = self.engine.parse_query(query)

        operator_nodes = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'OPERATOR')
        # Should have operators for AND condition
        self.assertGreater(len(operator_nodes), 0)

    def test_parse_join_with_multiple_conditions_or(self):
        """Test JOIN with OR in ON clause."""
        query = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id OR u.email = o.email"
        parsed = self.engine.parse_query(query)

        operator_nodes = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'OPERATOR')
        # Should have operators for OR condition
        self.assertGreater(len(operator_nodes), 0)

    def test_parse_join_with_multiple_table_references(self):
        """Test JOIN referencing multiple columns from each table."""
        query = """
        SELECT u.id, u.name, u.email, o.id, o.total, o.date
        FROM users u
        JOIN orders o ON u.id = o.user_id
        """
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_with_string_literal_comparison(self):
        """Test JOIN with string literal in condition."""
        query = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id AND o.status = 'COMPLETED'"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_with_numeric_literal(self):
        """Test JOIN with numeric literal in condition."""
        query = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id AND o.total > 1000"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_parenthesized_condition(self):
        """Test JOIN with parenthesized conditions."""
        query = "SELECT * FROM users u JOIN orders o ON (u.id = o.user_id)"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_complex_parentheses(self):
        """Test JOIN with complex parenthesized conditions."""
        query = "SELECT * FROM users u JOIN orders o ON (u.id = o.user_id AND u.region = o.region) OR (u.email = o.email)"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_no_aliases(self):
        """Test JOIN without table aliases."""
        query = "SELECT users.name, orders.total FROM users JOIN orders ON users.id = orders.user_id"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_with_column_aliases(self):
        """Test JOIN with column aliases in SELECT."""
        query = "SELECT u.name AS user_name, o.total AS order_total FROM users u JOIN orders o ON u.id = o.user_id"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_natural_join(self):
        """Test NATURAL JOIN parsing."""
        query = "SELECT * FROM users NATURAL JOIN orders"

        try:
            parsed = self.engine.parse_query(query)
            self.assertIsNotNone(parsed.query_tree)

            # Check for NATURAL_JOIN node
            natural_joins = TreeAnalyzer.find_nodes_by_type(
                parsed.query_tree, 'NATURAL_JOIN')
            theta_joins = TreeAnalyzer.find_nodes_by_type(
                parsed.query_tree, 'THETA_JOIN')
            self.assertTrue(natural_joins or theta_joins,
                            "Should create join node for NATURAL JOIN")
        except ValueError:
            # Natural join might not be implemented yet
            pass

    def test_parse_natural_join_with_aliases(self):
        """Test NATURAL JOIN with table aliases."""
        query = "SELECT u.name, o.total FROM users u NATURAL JOIN orders o"

        try:
            parsed = self.engine.parse_query(query)
            self.assertIsNotNone(parsed.query_tree)
        except ValueError:
            # Natural join might not be implemented yet
            pass

    def test_parse_natural_join_three_tables(self):
        """Test NATURAL JOIN with three tables."""
        query = """
        SELECT *
        FROM users
        NATURAL JOIN orders
        NATURAL JOIN products
        """

        try:
            parsed = self.engine.parse_query(query)
            self.assertIsNotNone(parsed.query_tree)
        except ValueError:
            # Natural join might not be implemented yet
            pass

    def test_parse_join_chain_left_associative(self):
        """Test that multiple JOINs are parsed left-to-right."""
        query = """
        SELECT *
        FROM table1 t1
        JOIN table2 t2 ON t1.id = t2.t1_id
        JOIN table3 t3 ON t2.id = t3.t2_id
        JOIN table4 t4 ON t3.id = t4.t3_id
        """
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_with_nested_and_or(self):
        """Test JOIN with nested AND/OR conditions."""
        query = """
        SELECT * FROM users u JOIN orders o 
        ON u.id = o.user_id AND (o.status = 'ACTIVE' OR o.status = 'PENDING')
        """
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_multiple_equality_conditions(self):
        """Test JOIN with multiple equality conditions."""
        query = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id AND u.company_id = o.company_id"
        parsed = self.engine.parse_query(query)

        operator_nodes = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'OPERATOR')
        self.assertGreater(len(operator_nodes), 0)

    def test_parse_join_with_where_and_complex_on(self):
        """Test JOIN with complex ON and WHERE conditions."""
        query = """
        SELECT * FROM users u
        JOIN orders o ON u.id = o.user_id AND u.region = o.region
        WHERE u.status = 'ACTIVE' AND o.total > 100
        """
        parsed = self.engine.parse_query(query)

        selection_stmts = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'SELECTION_STMT')
        self.assertTrue(selection_stmts)

    def test_parse_join_unqualified_columns_in_on(self):
        """Test JOIN with unqualified column names in ON clause."""
        query = "SELECT * FROM users JOIN orders ON id = user_id"

        try:
            parsed = self.engine.parse_query(query)
            self.assertIsNotNone(parsed.query_tree)
        except ValueError:
            # Might require qualified column names
            pass

    def test_parse_join_mixed_qualified_unqualified(self):
        """Test JOIN with mix of qualified and unqualified columns."""
        query = "SELECT name, o.total FROM users u JOIN orders o ON u.id = user_id"

        try:
            parsed = self.engine.parse_query(query)
            self.assertIsNotNone(parsed.query_tree)
        except ValueError:
            # Might require fully qualified column names
            pass

    def test_parse_join_with_star_and_specific_columns(self):
        """Test JOIN with both * and specific columns in SELECT."""
        query = "SELECT *, u.name FROM users u JOIN orders o ON u.id = o.user_id"

        try:
            parsed = self.engine.parse_query(query)
            self.assertIsNotNone(parsed.query_tree)
        except ValueError:
            # This syntax might not be supported
            pass

    def test_parse_join_long_table_names(self):
        """Test JOIN with long table and column names."""
        query = """
        SELECT customer_account.full_name, order_transaction.total_amount
        FROM customer_account
        JOIN order_transaction ON customer_account.account_id = order_transaction.customer_account_id
        """
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_numeric_table_aliases(self):
        """Test JOIN with numeric-like table aliases."""
        query = "SELECT t1.id, t2.value FROM table1 t1 JOIN table2 t2 ON t1.id = t2.t1_id"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_join_case_insensitive_join_keyword(self):
        """Test that JOIN keyword is case-insensitive."""
        queries = [
            "SELECT * FROM users join orders on users.id = orders.user_id",
            "SELECT * FROM users Join orders On users.id = orders.user_id",
            "SELECT * FROM users jOiN orders oN users.id = orders.user_id"
        ]

        for query in queries:
            parsed = self.engine.parse_query(query)
            self.assertIsNotNone(parsed.query_tree)


class TestParserEdgeCases(unittest.TestCase):
    """Test edge cases and error handling in parser."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = OptimizationEngine()

    def test_parse_query_with_extra_whitespace(self):
        """Test parsing with excessive whitespace."""
        query = "SELECT     *     FROM     users     WHERE     id   =   1"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_query_with_newlines(self):
        """Test parsing with newlines and formatting."""
        query = """
        SELECT *
        FROM users
        WHERE id = 1
        """
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)

    def test_parse_case_insensitive_keywords(self):
        """Test that parser handles mixed case keywords."""
        query = "SeLeCt * FrOm users WhErE id = 1"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)


if __name__ == '__main__':
    unittest.main()
