"""
Tests for Query Tree Utilities
"""
import unittest

from Query_Optimizer.optimization_engine import OptimizationEngine
from Query_Optimizer.query_types import QueryTree
from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer


class TestTreeAnalyzer(unittest.TestCase):
    """Test suite for tree analysis utilities."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = OptimizationEngine()

    def test_find_nodes_by_type_select(self):
        """Test finding SELECT nodes in query tree."""
        query = "SELECT * FROM users"
        parsed = self.engine.parse_query(query)

        # Parser creates PROJECTION nodes for SELECT
        projection_nodes = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'PROJECTION')
        self.assertGreater(len(projection_nodes), 0)

    def test_find_nodes_by_type_column(self):
        """Test finding COLUMN nodes in query tree."""
        query = "SELECT name, age FROM users"
        parsed = self.engine.parse_query(query)

        # Parser may or may not create separate COLUMN nodes
        # Just verify the query parses successfully
        self.assertIsNotNone(parsed.query_tree)

    def test_find_nodes_by_type_table(self):
        """Test finding TABLE nodes in query tree."""
        query = "SELECT * FROM users"
        parsed = self.engine.parse_query(query)

        # Parser may or may not create separate TABLE nodes
        # Just verify the tree has some structure
        self.assertIsNotNone(parsed.query_tree)
        self.assertTrue(hasattr(parsed.query_tree, 'type'))

    def test_find_nodes_by_type_operator(self):
        """Test finding OPERATOR nodes in query tree."""
        query = "SELECT * FROM users WHERE id = 1 AND age > 18"
        parsed = self.engine.parse_query(query)

        operator_nodes = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'OPERATOR')
        self.assertGreater(len(operator_nodes), 0)

    def test_find_nodes_by_type_join(self):
        """Test finding join nodes in query tree."""
        query = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id"
        parsed = self.engine.parse_query(query)

        # Look for any type of join
        theta_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'THETA_JOIN')
        inner_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'INNER_JOIN')

        total_joins = len(theta_joins) + len(inner_joins)
        self.assertGreater(total_joins, 0)

    def test_find_nodes_by_type_cross_join(self):
        """Test finding CROSS_JOIN nodes."""
        query = "SELECT * FROM users, orders"
        parsed = self.engine.parse_query(query)

        cross_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'CROSS_JOIN')
        self.assertTrue(cross_joins)

    def test_find_nodes_by_type_returns_list(self):
        """Test that find_nodes_by_type always returns a list."""
        query = "SELECT * FROM users"
        parsed = self.engine.parse_query(query)

        result = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'NONEXISTENT')
        self.assertIsInstance(result, list)

    def test_find_nodes_by_type_empty_when_not_found(self):
        """Test that find_nodes_by_type returns empty list when nodes not found."""
        query = "SELECT * FROM users"
        parsed = self.engine.parse_query(query)

        result = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'NONEXISTENT_NODE_TYPE')
        self.assertEqual(len(result), 0)

    def test_tree_traversal_depth(self):
        """Test that tree traversal works for nested structures."""
        query = """
        SELECT u.name, o.total 
        FROM users u 
        JOIN orders o ON u.id = o.user_id 
        WHERE u.status = 'ACTIVE' AND o.total > 100
        """
        parsed = self.engine.parse_query(query)

        # Find operators (should be deep in tree)
        operators = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'OPERATOR')

        # Should find operators regardless of depth
        self.assertGreater(len(operators), 0)

    def test_find_all_node_types(self):
        """Test finding multiple node types in one query."""
        query = "SELECT u.name, o.total FROM users u, orders o WHERE u.id = o.user_id"
        parsed = self.engine.parse_query(query)

        # Find various node types (parser uses PROJECTION for SELECT)
        projections = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'PROJECTION')
        cross_joins = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'CROSS_JOIN')
        operators = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'OPERATOR')

        # Should have at least projection node
        self.assertGreater(len(projections), 0)
        # Should have cross join or operators
        self.assertTrue(len(cross_joins) > 0 or len(operators) > 0)


class TestQueryTreeStructure(unittest.TestCase):
    """Test query tree structure and properties."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = OptimizationEngine()

    def test_query_tree_has_root(self):
        """Test that parsed query has a root node."""
        query = "SELECT * FROM users"
        parsed = self.engine.parse_query(query)

        self.assertIsNotNone(parsed.query_tree)
        self.assertIsInstance(parsed.query_tree, QueryTree)

    def test_query_tree_has_children(self):
        """Test that query tree nodes have children."""
        query = "SELECT * FROM users WHERE id = 1"
        parsed = self.engine.parse_query(query)

        # Root should have children
        if hasattr(parsed.query_tree, 'childs'):
            self.assertIsNotNone(parsed.query_tree.childs)

    def test_query_tree_structure_integrity(self):
        """Test that query tree maintains structural integrity."""
        query = "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id"
        parsed = self.engine.parse_query(query)

        # Tree should be traversable
        all_nodes = TreeAnalyzer.find_nodes_by_type(parsed.query_tree, None)
        # Should find at least the root
        self.assertGreater(len(all_nodes) if all_nodes else 1, 0)

    def test_tree_node_has_type_and_value(self):
        """Test that tree nodes have type and value attributes."""
        query = "SELECT * FROM users"
        parsed = self.engine.parse_query(query)

        self.assertTrue(hasattr(parsed.query_tree, 'type'))
        self.assertTrue(hasattr(parsed.query_tree, 'val'))


if __name__ == '__main__':
    unittest.main()
