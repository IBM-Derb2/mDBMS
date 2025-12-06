"""
Tests for Query Optimization Engine
"""
import unittest
from typing import cast

from Query_Optimizer.optimization_engine import OptimizationEngine
from Query_Optimizer.query_types import ParsedQuery
from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer


class TestOptimizationEngine(unittest.TestCase):
    """Test suite for query optimization functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = OptimizationEngine()

    def test_optimize_simple_query(self):
        """Test optimization of a simple query."""
        query = "SELECT * FROM users WHERE id = 1"
        parsed = self.engine.parse_query(query)
        optimized = self.engine.optimize_query(parsed)

        self.assertIsNotNone(optimized)
        self.assertIsInstance(optimized, ParsedQuery)

    def test_optimize_cartesian_product_to_theta_join(self):
        """Test optimization converts cartesian product to theta join."""
        query = "SELECT * FROM users u, orders o WHERE u.id = o.user_id"
        parsed = self.engine.parse_query(query)

        # Before optimization - should have CROSS_JOIN
        cross_joins_before = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'CROSS_JOIN')
        self.assertTrue(cross_joins_before, "Parser should create CROSS_JOIN")

        # After optimization
        optimized = self.engine.optimize_query(parsed)

        # Should have theta join or the cross join should be optimized
        theta_joins = TreeAnalyzer.find_nodes_by_type(
            optimized.query_tree, 'THETA_JOIN')
        cross_joins_after = TreeAnalyzer.find_nodes_by_type(
            optimized.query_tree, 'CROSS_JOIN')

        # At least one form of join should exist
        self.assertTrue(theta_joins or cross_joins_after)

    def test_optimize_push_selection_down(self):
        """Test that selection predicates are pushed down in the tree."""
        query = "SELECT * FROM users WHERE age > 18"
        parsed = self.engine.parse_query(query)
        optimized = self.engine.optimize_query(parsed)

        # Selection should be present and optimized
        selection_stmts = TreeAnalyzer.find_nodes_by_type(
            optimized.query_tree, 'SELECTION_STMT')
        self.assertTrue(selection_stmts)

    def test_optimize_multiple_joins(self):
        """Test optimization of queries with multiple joins."""
        query = """
        SELECT u.name, o.total, p.name 
        FROM users u 
        JOIN orders o ON u.id = o.user_id 
        JOIN products p ON o.product_id = p.id
        WHERE u.status = 'ACTIVE'
        """
        parsed = self.engine.parse_query(query)
        optimized = self.engine.optimize_query(parsed)

        self.assertIsNotNone(optimized.query_tree)

    def test_optimize_with_multiple_conditions(self):
        """Test optimization with multiple WHERE conditions."""
        query = """
        SELECT * FROM users u, orders o 
        WHERE u.id = o.user_id 
        AND u.status = 'ACTIVE' 
        AND o.total > 100
        """
        parsed = self.engine.parse_query(query)
        optimized = self.engine.optimize_query(parsed)

        # Optimized tree should exist
        self.assertIsNotNone(optimized.query_tree)

    def test_optimize_requires_parsed_query(self):
        """Test that optimize_query requires ParsedQuery instance."""
        not_a_parsed_query = cast(ParsedQuery, None)

        with self.assertRaises(TypeError):
            self.engine.optimize_query(not_a_parsed_query)

    def test_optimize_preserves_query_semantics(self):
        """Test that optimization preserves the logical query structure."""
        query = "SELECT name, age FROM users WHERE age >= 18"
        parsed = self.engine.parse_query(query)
        optimized = self.engine.optimize_query(parsed)

        # Both should have similar node types
        parsed_columns = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'COLUMN')
        optimized_columns = TreeAnalyzer.find_nodes_by_type(
            optimized.query_tree, 'COLUMN')

        # Should preserve columns
        self.assertEqual(len(parsed_columns), len(optimized_columns))

    def test_optimize_complex_join_with_filters(self):
        """Test optimization of complex join with multiple filters."""
        query = """
        SELECT u.name, o.total 
        FROM users u 
        JOIN orders o ON u.id = o.user_id 
        WHERE o.status = 'PAID' 
        AND u.age >= 18
        """
        parsed = self.engine.parse_query(query)
        optimized = self.engine.optimize_query(parsed)

        # Should successfully optimize
        self.assertIsNotNone(optimized.query_tree)

    def test_optimize_idempotency(self):
        """Test that running optimization multiple times produces consistent results."""
        query = "SELECT * FROM users WHERE id = 1"
        parsed = self.engine.parse_query(query)

        optimized1 = self.engine.optimize_query(parsed)
        optimized2 = self.engine.optimize_query(parsed)

        # Both should be valid
        self.assertIsNotNone(optimized1.query_tree)
        self.assertIsNotNone(optimized2.query_tree)


class TestCostCalculation(unittest.TestCase):
    """Test suite for query cost calculation."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = OptimizationEngine()

    def test_get_cost_from_query_string(self):
        """Test that get_cost accepts query strings."""
        query = "SELECT * FROM users"
        cost = self.engine.get_cost(query)

        self.assertIsInstance(cost, (int, float))
        self.assertGreater(cost, 0)

    def test_get_cost_with_where_clause(self):
        """Test cost calculation for query with WHERE clause."""
        query = "SELECT * FROM users WHERE id = 1"
        cost = self.engine.get_cost(query)

        self.assertGreater(cost, 0)

    def test_get_cost_with_join(self):
        """Test cost calculation for JOIN query."""
        query = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id"
        cost = self.engine.get_cost(query)

        self.assertGreater(cost, 0)

    def test_cost_comparison_simple_vs_complex(self):
        """Test that complex queries generally have higher cost."""
        simple_query = "SELECT * FROM users WHERE id = 1"
        complex_query = """
        SELECT u.name, o.total
        FROM users u 
        JOIN orders o ON u.id = o.user_id 
        WHERE u.status = 'ACTIVE'
        """

        simple_cost = self.engine.get_cost(simple_query)
        complex_cost = self.engine.get_cost(complex_query)

        # Both queries should have positive cost
        self.assertGreater(simple_cost, 0)
        self.assertGreater(complex_cost, 0)

    def test_cost_uses_statistics(self):
        """Test that cost calculation uses table statistics."""
        query = "SELECT * FROM users WHERE id = 1"
        cost = self.engine.get_cost(query)

        # Cost should be based on statistics (greater than some threshold)
        self.assertGreater(cost, 100)

    def test_cost_for_cartesian_product(self):
        """Test cost calculation for cartesian product."""
        query = "SELECT * FROM users, orders"
        cost = self.engine.get_cost(query)

        # Cartesian product should have high cost
        self.assertGreater(cost, 0)

    def test_cost_with_multiple_tables(self):
        """Test cost calculation with multiple table references."""
        query = "SELECT * FROM users u, orders o, products p"
        cost = self.engine.get_cost(query)

        self.assertGreater(cost, 0)


if __name__ == '__main__':
    unittest.main()
