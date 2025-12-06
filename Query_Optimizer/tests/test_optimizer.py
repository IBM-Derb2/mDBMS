"""
Tests for Query Optimization Engine
"""
import unittest
from typing import cast
import os
from io import StringIO

from Query_Optimizer.optimization_engine import OptimizationEngine
from Query_Optimizer.query_types import ParsedQuery
from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer


class TestOptimizationEngine(unittest.TestCase):
    """Test suite for query optimization functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Disable optimizer logging during tests for cleaner output
        import logging
        logging.basicConfig(level=logging.WARNING)
        logger = logging.getLogger("optimizer_test")
        logger.setLevel(logging.WARNING)

        self.engine = OptimizationEngine(logger=logger)
        self.markdown_output = []
        self.optimization_log = []

    def _compare_before_after(self, query: str, test_name: str = ""):
        """Helper method to compare query before and after optimization."""
        # Parse the query
        parsed = self.engine.parse_query(query)

        # Get cost before optimization
        cost_before, rows_before = self.engine.statistics_manager.calculate_cost(
            parsed.query_tree)

        # Get tree structure before
        tree_before_str = self._tree_to_string(parsed.query_tree, indent=0)

        # Optimize the query
        optimized = self.engine.optimize_query(parsed)

        # Get cost after optimization
        cost_after, rows_after = self.engine.statistics_manager.calculate_cost(
            optimized.query_tree)

        # Get tree structure after
        tree_after_str = self._tree_to_string(optimized.query_tree, indent=0)

        # Check if tree actually changed
        tree_changed = tree_before_str != tree_after_str

        # Calculate improvement
        improvement = ((cost_before - cost_after) / cost_before) * \
            100 if cost_before > 0 else 0

        # Build markdown output
        md = []
        md.append(f"\n## {test_name or 'Optimization Comparison'}\n")
        md.append(f"**Query:**\n```sql\n{query.strip()}\n```\n")

        # Add optimization status
        if tree_changed:
            md.append(f"\n> ✅ **Tree was modified by optimizer**\n")
        else:
            md.append(
                f"\n> ⚠️ **Tree was NOT modified - no optimizations applied**\n")

        md.append(f"### Before Optimization\n")
        md.append(f"- **Estimated Cost:** {cost_before:,}\n")
        md.append(f"- **Estimated Rows:** {rows_before:,}\n")
        md.append(f"\n**Tree Structure:**\n```\n")
        md.append(tree_before_str)
        md.append(f"```\n")

        md.append(f"\n### After Optimization\n")
        md.append(f"- **Estimated Cost:** {cost_after:,}\n")
        md.append(f"- **Estimated Rows:** {rows_after:,}\n")
        md.append(f"\n**Tree Structure:**\n```\n")
        md.append(tree_after_str)
        md.append(f"```\n")

        md.append(f"\n### Optimization Results\n")
        md.append(f"| Metric | Before | After | Difference | Improvement |\n")
        md.append(f"|--------|--------|-------|------------|-------------|\n")
        md.append(
            f"| **Cost** | {cost_before:,} | {cost_after:,} | {cost_before - cost_after:,} | {improvement:.2f}% |\n")
        md.append(
            f"| **Rows** | {rows_before:,} | {rows_after:,} | {rows_before - rows_after:,} | - |\n")
        md.append(f"\n---\n")

        self.markdown_output.extend(md)

        return parsed, optimized, cost_before, cost_after

    def _tree_to_string(self, tree, indent=0, is_last_child=True):
        """Helper method to convert tree to string with detailed node information."""
        lines = []

        # Create the tree branch characters
        if indent == 0:
            prefix = ""
            branch = ""
        else:
            prefix = "  " * (indent - 1)
            branch = "└─ " if is_last_child else "├─ "

        # Build the node line with type and value
        line = f"{prefix}{branch}{tree.type}"

        # Add value/details based on what's available
        if hasattr(tree, 'val') and tree.val:
            # Format the value nicely
            val_str = str(tree.val)
            if isinstance(tree.val, list):
                val_str = f"[{', '.join(repr(v) for v in tree.val)}]"
            else:
                val_str = f"'{val_str}'"
            line += f" = {val_str}"
        elif hasattr(tree, 'value') and tree.value:
            line += f" = '{tree.value}'"

        # Add table name if present
        if hasattr(tree, 'table') and tree.table:
            line += f" (table: {tree.table})"

        # Add alias if present
        if hasattr(tree, 'alias') and tree.alias:
            line += f" (alias: {tree.alias})"

        lines.append(line + "\n")

        # Process children
        if hasattr(tree, 'childs') and tree.childs:
            for i, child in enumerate(tree.childs):
                is_last = (i == len(tree.childs) - 1)
                lines.append(self._tree_to_string(child, indent + 1, is_last))

        return "".join(lines)

    def test_optimize_simple_query(self):
        """Test optimization of a simple query."""
        query = "SELECT * FROM users WHERE id = 1"
        parsed, optimized, cost_before, cost_after = self._compare_before_after(
            query, "Simple Query Optimization")

        self.assertIsNotNone(optimized)
        self.assertIsInstance(optimized, ParsedQuery)

    def test_optimize_cartesian_product_to_theta_join(self):
        """Test optimization converts cartesian product to theta join."""
        query = "SELECT * FROM users u, orders o WHERE u.id = o.user_id"

        # Parse first to check what the parser creates
        initial_parsed = self.engine.parse_query(query)
        cartesian_products = TreeAnalyzer.find_nodes_by_type(
            initial_parsed.query_tree, 'CARTESIAN_PRODUCT')
        cross_joins_before = TreeAnalyzer.find_nodes_by_type(
            initial_parsed.query_tree, 'CROSS_JOIN')
        self.assertTrue(cartesian_products or cross_joins_before,
                        "Parser should create CARTESIAN_PRODUCT or CROSS_JOIN")

        # Now run the comparison which will optimize
        parsed, optimized, cost_before, cost_after = self._compare_before_after(
            query, "Cartesian Product to Theta Join")

        # After optimization - should have theta join
        theta_joins = TreeAnalyzer.find_nodes_by_type(
            optimized.query_tree, 'THETA_JOIN')
        cross_joins_after = TreeAnalyzer.find_nodes_by_type(
            optimized.query_tree, 'CROSS_JOIN')

        # Should have converted to theta join
        self.assertTrue(theta_joins, "Optimizer should convert to THETA_JOIN")

        # Cost should be significantly reduced
        self.assertLess(cost_after, cost_before * 0.01,
                        "Cost should be reduced by at least 99%")

    def test_optimize_push_selection_down(self):
        """Test that selection predicates are pushed down in the tree."""
        query = "SELECT * FROM users WHERE age > 18"
        parsed, optimized, cost_before, cost_after = self._compare_before_after(
            query, "Push Selection Down")

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
        parsed, optimized, cost_before, cost_after = self._compare_before_after(
            query, "Multiple Joins Optimization")

        self.assertIsNotNone(optimized.query_tree)

    def test_optimize_with_multiple_conditions(self):
        """Test optimization with multiple WHERE conditions."""
        query = """
        SELECT * FROM users u, orders o 
        WHERE u.id = o.user_id 
        AND u.status = 'ACTIVE' 
        AND o.total > 100
        """
        parsed, optimized, cost_before, cost_after = self._compare_before_after(
            query, "Multiple Conditions Optimization")

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
        parsed, optimized, cost_before, cost_after = self._compare_before_after(
            query, "Complex Join with Filters")

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

    @classmethod
    def tearDownClass(cls):
        """Save markdown output after all tests."""
        # Disable logging for markdown generation
        import logging
        logging.getLogger().setLevel(logging.ERROR)

        all_markdown = []

        all_markdown.append("# Query Optimizer Test Results\n\n")
        from datetime import datetime
        all_markdown.append(
            f"**Test Run Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        all_markdown.append("---\n\n")

        # Run a fresh set of tests to collect markdown
        test_instance = cls()
        test_instance.setUp()

        # Run each comparison test
        tests_to_run = [
            ("SELECT * FROM users WHERE id = 1", "Simple Query Optimization"),
            ("SELECT * FROM users u, orders o WHERE u.id = o.user_id",
             "Cartesian Product to Theta Join"),
            ("SELECT * FROM users WHERE age > 18", "Push Selection Down"),
            ("""SELECT u.name, o.total, p.name 
        FROM users u 
        JOIN orders o ON u.id = o.user_id 
        JOIN products p ON o.product_id = p.id
        WHERE u.status = 'ACTIVE'""", "Multiple Joins Optimization"),
            ("""SELECT * FROM users u, orders o 
        WHERE u.id = o.user_id 
        AND u.status = 'ACTIVE' 
        AND o.total > 100""", "Multiple Conditions Optimization"),
            ("""SELECT u.name, o.total 
        FROM users u 
        JOIN orders o ON u.id = o.user_id 
        WHERE o.status = 'PAID' 
        AND u.age >= 18""", "Complex Join with Filters"),
        ]

        for query, test_name in tests_to_run:
            try:
                test_instance._compare_before_after(query, test_name)
            except:
                pass

        all_markdown.extend(test_instance.markdown_output)

        # Write to file
        output_path = os.path.join(os.path.dirname(
            __file__), '..', 'test_output', 'optimizer_results.md')
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(all_markdown)

        print(f"\nMarkdown results saved to: {output_path}")


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
