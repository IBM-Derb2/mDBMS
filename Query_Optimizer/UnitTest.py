import unittest
from typing import Dict, List, Tuple, cast
import os

from Query_Optimizer.lib.helpers.tokenizer import SQLTokenizer, SQLToken
from Query_Optimizer.lib.parse_query import internal_parse_query
from Query_Optimizer.lib.get_cost import internal_get_cost
from Query_Optimizer.lib.cost import cost_calculator
from Query_Optimizer.lib.cost.cost_calculator import calculate_node_cost
from Query_Optimizer.lib.optimization.rules.selection_rules import SelectionRule
from Query_Optimizer.lib.optimization.rules.distribution_rules import DistributionRule
from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer
from Query_Optimizer.optimization_engine import OptimizationEngine
from Query_Optimizer.query_types import QueryTree, ParsedQuery

# Markdown output file
MARKDOWN_OUTPUT_FILE = "Query_Optimizer/test_results.md"


def _token_snapshot(tokens: List[SQLToken], length: int) -> List[Tuple[str, str]]:
    """Return (type, value) pairs for the first `length` tokens."""
    return [(tokens[i].type, tokens[i].value) for i in range(length)]


def _report_test_io(test_name: str, inputs: Dict[str, object], outputs: Dict[str, object]) -> None:
    """Write structured input/output pairs to markdown file."""
    with open(MARKDOWN_OUTPUT_FILE, 'a', encoding='utf-8') as f:
        f.write(f"\n## {test_name}\n\n")
        f.write(
            f"**Description:** {test_name.split('.')[-1].replace('_', ' ').title()}\n\n")
        f.write(
            f"**Goal:** Verify the behavior of {test_name.split('.')[0]}\n\n")
        f.write(f"**Method:** Unit test\n\n")
        f.write(f"**Success Criterion:** Test passes without assertion errors\n\n")
        f.write(f"**Input:** {inputs}\n\n")
        f.write(f"**Expected Output:** {outputs}\n\n")
        f.write(f"**Results:** {'Pass' if outputs else 'N/A'}\n\n")
        f.write("---\n")


def _build_simple_select_tree() -> QueryTree:
    """Create a simple SELECT QueryTree for deterministic cost tests."""
    star_column = QueryTree(type='COLUMN', val='*')
    column_container = QueryTree(type='COLUMNS', val='', childs=[star_column])

    table_node = QueryTree(type='TABLE', val='users')
    from_node = QueryTree(type='FROM', val='', childs=[table_node])

    left_operand = QueryTree(type='COLUMN', val='users.id')
    right_operand = QueryTree(type='LITERAL', val='1')
    equals_operator = QueryTree(type='OPERATOR', val='=', childs=[
                                left_operand, right_operand])
    where_node = QueryTree(type='WHERE', val='', childs=[equals_operator])

    return QueryTree(type='SELECT', val='SELECT', childs=[column_container, from_node, where_node])


class SQLTokenizerTests(unittest.TestCase):
    def test_tokenize_ignores_comments_and_captures_literals(self):
        # Arrange
        query = """
		SELECT name, 'ACTIVE' as status -- inline comment
		FROM users /* block comment */
		WHERE age >= 18;
		""".strip()

        tokens = SQLTokenizer(query).tokenize()
        snapshot = _token_snapshot(tokens, 8)

        self.assertEqual(
            snapshot,
            [
                        ('KEYWORD', 'SELECT'),
                        ('IDENTIFIER', 'name'),
                        ('PUNCTUATION', ','),
                        ('STRING', 'ACTIVE'),
                        ('KEYWORD', 'AS'),
                        ('IDENTIFIER', 'status'),
                        ('KEYWORD', 'FROM'),
                        ('IDENTIFIER', 'users'),
            ]
        )
        _report_test_io(
            "SQLTokenizerTests.test_tokenize_ignores_comments_and_captures_literals",
            {"query": query},
            {"tokens": snapshot}
        )

    def test_tokenize_unclosed_string_raises_value_error(self):
        # Arrange
        bad_query = "SELECT 'oops"

        with self.assertRaises(ValueError):
            SQLTokenizer(bad_query).tokenize()
        _report_test_io(
            "SQLTokenizerTests.test_tokenize_unclosed_string_raises_value_error",
            {"query": bad_query},
            {"error": "ValueError"}
        )


class InternalParseQueryTests(unittest.TestCase):
    def test_parse_select_creates_where_branch(self):
        # Arrange
        query = "SELECT * FROM users WHERE id = 10"

        parsed = internal_parse_query(query)
        where_nodes = TreeAnalyzer.find_nodes_by_type(
            parsed.query_tree, 'WHERE')

        self.assertTrue(
            where_nodes, "WHERE node should exist for simple filter")
        _report_test_io(
            "InternalParseQueryTests.test_parse_select_creates_where_branch",
            {"query": query},
            {"where_count": len(where_nodes)}
        )

    def test_parse_query_rejects_empty_string(self):
        # Arrange
        query = "   "

        with self.assertRaises(ValueError):
            internal_parse_query(query)
        _report_test_io(
            "InternalParseQueryTests.test_parse_query_rejects_empty_string",
            {"query": query},
            {"error": "ValueError"}
        )


class OptimizationEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = OptimizationEngine()

    def test_parse_query_returns_parsed_query_instance(self):
        # Arrange
        query = "SELECT * FROM users"

        parsed = self.engine.parse_query(query)

        self.assertIsInstance(parsed, ParsedQuery)
        _report_test_io(
            "OptimizationEngineTests.test_parse_query_returns_parsed_query_instance",
            {"query": query},
            {"parsed_type": type(parsed).__name__}
        )

    def test_parse_query_invalid_keyword_raises_value_error(self):
        # Arrange
        query = "RANDOM something"

        with self.assertRaises(ValueError):
            self.engine.parse_query(query)
        _report_test_io(
            "OptimizationEngineTests.test_parse_query_invalid_keyword_raises_value_error",
            {"query": query},
            {"error": "ValueError"}
        )

    def test_optimize_query_requires_parsed_query_instance(self):
        # Arrange
        not_a_parsed_query = cast(ParsedQuery, None)

        with self.assertRaises(TypeError):
            self.engine.optimize_query(not_a_parsed_query)
        _report_test_io(
            "OptimizationEngineTests.test_optimize_query_requires_parsed_query_instance",
            {"parsed_query": not_a_parsed_query},
            {"error": "TypeError"}
        )

    def test_optimize_query_converts_cartesian_product_to_join(self):
        # Arrange
        query = "SELECT * FROM users u, orders o WHERE u.id = o.user_id"
        parsed = self.engine.parse_query(query)

        optimized = self.engine.optimize_query(parsed)
        from_nodes = TreeAnalyzer.find_nodes_by_type(
            optimized.query_tree, 'FROM')
        join_nodes = TreeAnalyzer.find_nodes_by_type(
            optimized.query_tree, 'JOIN')

        self.assertTrue(
            join_nodes, "JOIN node should be created for theta join condition")
        self.assertEqual(from_nodes[0].childs[0].type, 'JOIN')
        _report_test_io(
            "OptimizationEngineTests.test_optimize_query_converts_cartesian_product_to_join",
            {"query": query},
            {"join_count": len(
                join_nodes), "from_child_type": from_nodes[0].childs[0].type}
        )


class CostCalculatorTests(unittest.TestCase):
    def setUp(self):
        self._original_use_stats = cost_calculator.USE_STATISTICS
        cost_calculator.USE_STATISTICS = False

    def tearDown(self):
        cost_calculator.USE_STATISTICS = self._original_use_stats

    def test_internal_get_cost_rejects_raw_query_strings(self):
        # Arrange
        query = "SELECT * FROM users"

        with self.assertRaises(TypeError):
            internal_get_cost(query)
        _report_test_io(
            "CostCalculatorTests.test_internal_get_cost_rejects_raw_query_strings",
            {"query": query},
            {"error": "TypeError"}
        )

    def test_calculate_node_cost_accumulates_child_costs(self):
        # Arrange
        tree = _build_simple_select_tree()

        total_cost = calculate_node_cost(tree)

        self.assertEqual(total_cost, 152)
        _report_test_io(
            "CostCalculatorTests.test_calculate_node_cost_accumulates_child_costs",
            {"tree": tree.type},
            {"total_cost": total_cost}
        )


class DistributionRuleTests(unittest.TestCase):
    def test_distribution_rule_detects_selection_over_join(self):
        # Arrange
        query = "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = 'PAID'"
        parsed = internal_parse_query(query)
        rule = DistributionRule()

        can_apply = rule.can_apply(parsed.query_tree)

        self.assertTrue(can_apply)
        _report_test_io(
            "DistributionRuleTests.test_distribution_rule_detects_selection_over_join",
            {"query": query},
            {"can_apply": can_apply}
        )

    def test_distribution_rule_apply_preserves_join_structure(self):
        # Arrange
        query = "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = 'PAID'"
        parsed = internal_parse_query(query)
        rule = DistributionRule()

        optimized_tree = rule.apply(parsed.query_tree)
        join_nodes = TreeAnalyzer.find_nodes_by_type(optimized_tree, 'JOIN')

        self.assertTrue(
            join_nodes, "Distribution rule should not remove joins")
        self.assertEqual(optimized_tree.type, 'SELECT')
        _report_test_io(
            "DistributionRuleTests.test_distribution_rule_apply_preserves_join_structure",
            {"query": query},
            {"join_count": len(join_nodes),
             "root_type": optimized_tree.type}
        )


class SelectionRuleTests(unittest.TestCase):
    def test_selection_rule_detects_applicability(self):
        # Arrange
        query = "SELECT * FROM users u, orders o WHERE u.id = o.user_id"
        parsed = internal_parse_query(query)
        rule = SelectionRule()

        can_apply = rule.can_apply(parsed.query_tree)

        self.assertTrue(can_apply)
        _report_test_io(
            "SelectionRuleTests.test_selection_rule_detects_applicability",
            {"query": query},
            {"can_apply": can_apply}
        )

    def test_selection_rule_converts_cartesian_product_into_join(self):
        # Arrange
        query = "SELECT * FROM users u, orders o WHERE u.id = o.user_id"
        parsed = internal_parse_query(query)
        rule = SelectionRule()

        optimized_tree = rule.apply(parsed.query_tree)
        from_nodes = TreeAnalyzer.find_nodes_by_type(optimized_tree, 'FROM')
        join_nodes = TreeAnalyzer.find_nodes_by_type(optimized_tree, 'JOIN')

        self.assertTrue(
            join_nodes, "Theta join must be created from selection condition")
        self.assertEqual(from_nodes[0].childs[0].type, 'JOIN')
        _report_test_io(
            "SelectionRuleTests.test_selection_rule_converts_cartesian_product_into_join",
            {"query": query},
            {"join_count": len(
                join_nodes), "from_child_type": from_nodes[0].childs[0].type}
        )


if __name__ == '__main__':
    # Initialize markdown output file
    with open(MARKDOWN_OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# Query Optimizer Unit Test Results\n\n")
        f.write(
            f"Test run date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n")

    unittest.main()
