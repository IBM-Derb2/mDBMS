"""
Query Optimizer - Main Test Suite
Run all tests with: python Query_Optimizer/UnitTest.py
Run specific tests: python Query_Optimizer/UnitTest.py --tokenizer
                    python Query_Optimizer/UnitTest.py --parser
                    python Query_Optimizer/UnitTest.py --optimizer
                    python Query_Optimizer/UnitTest.py --rules
                    python Query_Optimizer/UnitTest.py --tree-utils
Run with tree output: python Query_Optimizer/UnitTest.py --parser --show-trees
"""
import unittest
import sys
import os
import argparse
from datetime import datetime

# Add parent directory to path so imports work when running this file directly
if __name__ == '__main__':
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

# Import test modules
from Query_Optimizer.tests import (
    test_tokenizer,
    test_parser,
    test_optimizer,
    test_optimization_rules,
    test_tree_utils
)

# Module mapping for easy access
TEST_MODULES = {
    'tokenizer': test_tokenizer,
    'parser': test_parser,
    'optimizer': test_optimizer,
    'rules': test_optimization_rules,
    'tree-utils': test_tree_utils,
}


def format_tree(node, level=0, prefix=""):
    """Format a query tree for visualization.

    Args:
        node: The tree node to format.
        level: Current indentation level.
        prefix: Prefix for the current line.

    Returns:
        str: Formatted tree string.
    """
    if node is None:
        return ""

    indent = "  " * level
    result = f"{indent}{prefix}{node.type}"
    if node.val and node.val != node.type:
        result += f" = '{node.val}'"
    result += "\n"

    if hasattr(node, 'childs') and node.childs:
        for i, child in enumerate(node.childs):
            is_last = (i == len(node.childs) - 1)
            child_prefix = "└─ " if is_last else "├─ "
            result += format_tree(child, level + 1, child_prefix)

    return result


def write_tokenizer_report(f):
    """Write tokenizer-specific test results."""
    from Query_Optimizer.lib.helpers.tokenizer import SQLTokenizer

    f.write("## Tokenizer Tests\n\n")
    f.write("### Sample Tokenizations\n\n")

    samples = [
        "SELECT * FROM users",
        "SELECT name, age FROM users WHERE age > 18",
        "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id"
    ]

    for query in samples:
        f.write(f"#### Query: `{query}`\n\n")
        try:
            tokens = SQLTokenizer(query).tokenize()
            f.write("**Tokens:**\n\n")
            f.write("| Type | Value | Position |\n")
            f.write("|------|-------|----------|\n")
            for i, token in enumerate(tokens[:20]):  # Limit to first 20 tokens
                f.write(
                    f"| {token.type} | `{token.value}` | {token.position} |\n")
            if len(tokens) > 20:
                f.write(f"\n*... and {len(tokens) - 20} more tokens*\n")
            f.write("\n")
        except Exception as e:
            f.write(f"**Error:** {str(e)}\n\n")


def write_parser_report(f, show_trees=False):
    """Write parser-specific test results with optional tree visualization."""
    from Query_Optimizer.optimization_engine import OptimizationEngine

    f.write("## Parser Tests\n\n")
    f.write("### Sample Parse Trees\n\n")

    if show_trees:
        samples = [
            ("Simple SELECT", "SELECT * FROM users"),
            ("SELECT with WHERE", "SELECT * FROM users WHERE id = 1"),
            ("SELECT with Multiple Columns",
             "SELECT name, age, email FROM users WHERE age > 18"),
            ("Basic JOIN", "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id"),
            ("JOIN with WHERE", "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id WHERE o.total > 100"),
            ("JOIN with Complex ON",
             "SELECT * FROM users u JOIN orders o ON u.id = o.user_id AND u.status = 'ACTIVE'"),
            ("Self-Join", "SELECT e1.name, e2.name FROM employees e1 JOIN employees e2 ON e1.manager_id = e2.id"),
            ("Multiple JOINs", "SELECT u.name, o.total, p.name FROM users u JOIN orders o ON u.id = o.user_id JOIN products p ON o.product_id = p.id"),
            ("Cross Join (Implicit)", "SELECT * FROM users, orders"),
            ("Cross Join with WHERE",
             "SELECT * FROM users, orders WHERE users.id = orders.user_id"),
            ("NATURAL JOIN", "SELECT * FROM users NATURAL JOIN orders"),
            ("Complex WHERE with AND/OR",
             "SELECT * FROM users WHERE (age > 18 AND status = 'ACTIVE') OR balance > 1000"),
            ("JOIN with Nested Conditions",
             "SELECT * FROM users u JOIN orders o ON u.id = o.user_id AND (o.status = 'ACTIVE' OR o.status = 'PENDING')"),
            ("Four Table JOIN", "SELECT * FROM t1 JOIN t2 ON t1.id = t2.t1_id JOIN t3 ON t2.id = t3.t2_id JOIN t4 ON t3.id = t4.t3_id")
        ]

        engine = OptimizationEngine()

        for title, query in samples:
            f.write(f"#### {title}\n\n")
            f.write(f"**Query:** `{query}`\n\n")
            try:
                parsed = engine.parse_query(query)
                f.write("**Parse Tree Structure:**\n\n")
                f.write("```\n")
                f.write(format_tree(parsed.query_tree, 0))
                f.write("```\n\n")
            except Exception as e:
                f.write(f"**Parse Error:** {str(e)}\n\n")
    else:
        f.write("*Run with --show-trees flag to see parse tree visualizations*\n\n")


def write_optimizer_report(f):
    """Write optimizer-specific test results."""
    from Query_Optimizer.optimization_engine import OptimizationEngine
    import logging

    # Disable logging during report generation
    logging.getLogger().setLevel(logging.ERROR)

    f.write("## Optimizer Tests\n\n")

    # Helper function to format tree with node details
    def tree_to_string(tree, indent=0, is_last_child=True):
        lines = []
        if indent == 0:
            prefix = ""
            branch = ""
        else:
            prefix = "  " * (indent - 1)
            branch = "└─ " if is_last_child else "├─ "

        line = f"{prefix}{branch}{tree.type}"

        if hasattr(tree, 'val') and tree.val:
            val_str = str(tree.val)
            if isinstance(tree.val, list):
                val_str = f"[{', '.join(repr(v) for v in tree.val)}]"
            else:
                val_str = f"'{val_str}'"
            line += f" = {val_str}"
        elif hasattr(tree, 'value') and tree.value:
            line += f" = '{tree.value}'"

        if hasattr(tree, 'table') and tree.table:
            line += f" (table: {tree.table})"

        if hasattr(tree, 'alias') and tree.alias:
            line += f" (alias: {tree.alias})"

        lines.append(line + "\n")

        if hasattr(tree, 'childs') and tree.childs:
            for i, child in enumerate(tree.childs):
                is_last = (i == len(tree.childs) - 1)
                lines.append(tree_to_string(child, indent + 1, is_last))

        return "".join(lines)

    # Test queries with descriptions
    test_cases = [
        ("Simple Query", "SELECT * FROM users WHERE id = 1"),
        ("Cartesian Product to Theta Join",
         "SELECT * FROM users u, orders o WHERE u.id = o.user_id"),
        ("Selection Pushdown", "SELECT * FROM users WHERE age > 18"),
        ("Multiple Conditions", """SELECT * FROM users u, orders o 
        WHERE u.id = o.user_id 
        AND u.status = 'ACTIVE' 
        AND o.total > 100"""),
        ("Complex Join", """SELECT u.name, o.total 
        FROM users u 
        JOIN orders o ON u.id = o.user_id 
        WHERE o.status = 'PAID' 
        AND u.age >= 18"""),
    ]

    engine = OptimizationEngine()

    for title, query in test_cases:
        f.write(f"### {title}\n\n")
        f.write(f"**Query:**\n```sql\n{query.strip()}\n```\n\n")

        try:
            # Parse and get before state
            parsed = engine.parse_query(query)
            cost_before, rows_before = engine.statistics_manager.calculate_cost(
                parsed.query_tree)
            tree_before = tree_to_string(parsed.query_tree, 0)

            # Optimize
            optimized = engine.optimize_query(parsed)
            cost_after, rows_after = engine.statistics_manager.calculate_cost(
                optimized.query_tree)
            tree_after = tree_to_string(optimized.query_tree, 0)

            # Check if changed
            tree_changed = tree_before != tree_after
            improvement = ((cost_before - cost_after) /
                           cost_before) * 100 if cost_before > 0 else 0

            if tree_changed:
                f.write("> ✅ **Tree was modified by optimizer**\n\n")
            else:
                f.write(
                    "> ⚠️ **Tree was NOT modified - no optimizations applied**\n\n")

            f.write("#### Before Optimization\n\n")
            f.write(f"- **Estimated Cost:** {cost_before:,}\n")
            f.write(f"- **Estimated Rows:** {rows_before:,}\n\n")
            f.write("**Tree Structure:**\n```\n")
            f.write(tree_before)
            f.write("```\n\n")

            f.write("#### After Optimization\n\n")
            f.write(f"- **Estimated Cost:** {cost_after:,}\n")
            f.write(f"- **Estimated Rows:** {rows_after:,}\n\n")
            f.write("**Tree Structure:**\n```\n")
            f.write(tree_after)
            f.write("```\n\n")

            f.write("#### Optimization Results\n\n")
            f.write("| Metric | Before | After | Difference | Improvement |\n")
            f.write("|--------|--------|-------|------------|-----------|\n")
            f.write(
                f"| **Cost** | {cost_before:,} | {cost_after:,} | {cost_before - cost_after:,} | {improvement:.2f}% |\n")
            f.write(
                f"| **Rows** | {rows_before:,} | {rows_after:,} | {rows_before - rows_after:,} | - |\n\n")
            f.write("---\n\n")

        except Exception as e:
            f.write(f"**Error:** {str(e)}\n\n")
            f.write("---\n\n")


def write_rules_report(f):
    """Write optimization rules test results."""
    f.write("## Optimization Rules Tests\n\n")
    f.write("### Rules Tested\n\n")
    f.write("- [x] Selection Rule (pushdown optimizations)\n")
    f.write("- [x] Distribution Rule (predicate distribution)\n")
    f.write("- [x] Join Rule (join reordering)\n")
    f.write("- [x] Projection Rule (column pruning)\n\n")


def write_tree_utils_report(f):
    """Write tree utilities test results."""
    f.write("## Tree Utilities Tests\n\n")
    f.write("### Tested Functionality\n\n")
    f.write("- [x] Node finding by type\n")
    f.write("- [x] Tree traversal algorithms\n")
    f.write("- [x] Tree structure validation\n")
    f.write("- [x] Node property access\n\n")


def generate_module_reports(result, modules, output_dir, show_trees=False):
    """Generate separate reports for each test module.

    Args:
        result: unittest.TestResult object.
        modules: List of module names.
        output_dir: Directory for output files.
        show_trees: Whether to include tree visualizations.
    """
    from Query_Optimizer.optimization_engine import OptimizationEngine

    for module_name in modules:
        if module_name not in TEST_MODULES:
            continue

        report_file = os.path.join(output_dir, f"{module_name}_results.md")

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(
                f"# {module_name.replace('-', ' ').title()} Test Results\n\n")
            f.write(
                f"**Test Run Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")

            # Module-specific content
            if module_name == 'tokenizer':
                write_tokenizer_report(f)
            elif module_name == 'parser':
                write_parser_report(f, show_trees)
            elif module_name == 'optimizer':
                write_optimizer_report(f)
            elif module_name == 'rules':
                write_rules_report(f)
            elif module_name == 'tree-utils':
                write_tree_utils_report(f)

        print(f"[OK] {module_name.title()} report: {report_file}")


def generate_markdown_report(result, modules=None, output_dir='Query_Optimizer/test_output'):
    """Generate a markdown report of test results.

    Args:
        result: unittest.TestResult object.
        modules: List of modules that were tested.
        output_dir: Directory for output files.
    """
    report_file = os.path.join(output_dir, "test_results.md")

    module_names = modules or list(TEST_MODULES.keys())

    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# Query Optimizer Test Results\n\n")
        f.write(
            f"**Test Run Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Modules Tested:** {', '.join(module_names)}\n\n")
        f.write("---\n\n")

        # Summary
        f.write("## Summary\n\n")
        f.write(f"- **Total Tests:** {result.testsRun}\n")
        f.write(
            f"- **Passed:** {result.testsRun - len(result.failures) - len(result.errors)}\n")
        f.write(f"- **Failed:** {len(result.failures)}\n")
        f.write(f"- **Errors:** {len(result.errors)}\n")
        f.write(f"- **Skipped:** {len(result.skipped)}\n\n")

        # Success rate
        if result.testsRun > 0:
            success_rate = ((result.testsRun - len(result.failures) -
                            len(result.errors)) / result.testsRun) * 100
            f.write(f"**Success Rate:** {success_rate:.2f}%\n\n")

        f.write("---\n\n")

        # Test Categories
        f.write("## Test Categories\n\n")

        if 'tokenizer' in module_names:
            f.write("### 1. Tokenizer Tests\n")
            f.write("- SQL tokenization and lexical analysis\n")
            f.write("- Comment handling (inline and block)\n")
            f.write("- String literal and numeric parsing\n")
            f.write("- Error handling for malformed queries\n\n")

        if 'parser' in module_names:
            f.write("### 2. Parser Tests\n")
            f.write("- SQL query parsing and AST generation\n")
            f.write("- Support for SELECT, JOIN, WHERE clauses\n")
            f.write("- Handling of complex nested conditions\n")
            f.write("- Error handling for invalid syntax\n\n")

        if 'optimizer' in module_names:
            f.write("### 3. Optimizer Tests\n")
            f.write("- Query optimization strategies\n")
            f.write("- Cartesian product to theta join conversion\n")
            f.write("- Selection and projection pushdown\n")
            f.write("- Query cost estimation\n\n")

        if 'rules' in module_names:
            f.write("### 4. Optimization Rules Tests\n")
            f.write("- Selection rule application\n")
            f.write("- Distribution rule application\n")
            f.write("- Join reordering strategies\n")
            f.write("- Projection optimization\n\n")

        if 'tree-utils' in module_names:
            f.write("### 5. Tree Utilities Tests\n")
            f.write("- Query tree traversal and analysis\n")
            f.write("- Node finding and filtering\n")
            f.write("- Tree structure integrity\n\n")

        # Failures
        if result.failures:
            f.write("---\n\n")
            f.write("## Failures\n\n")
            for test, traceback in result.failures:
                f.write(f"### {test}\n\n")
                f.write("```\n")
                f.write(traceback)
                f.write("```\n\n")

        # Errors
        if result.errors:
            f.write("---\n\n")
            f.write("## Errors\n\n")
            for test, traceback in result.errors:
                f.write(f"### {test}\n\n")
                f.write("```\n")
                f.write(traceback)
                f.write("```\n\n")

        f.write("---\n\n")
        f.write("## Test Modules\n\n")
        if 'tokenizer' in module_names:
            f.write("- `test_tokenizer.py` - SQL tokenization tests\n")
        if 'parser' in module_names:
            f.write("- `test_parser.py` - SQL parsing tests\n")
        if 'optimizer' in module_names:
            f.write("- `test_optimizer.py` - Query optimization tests\n")
        if 'rules' in module_names:
            f.write("- `test_optimization_rules.py` - Optimization rule tests\n")
        if 'tree-utils' in module_names:
            f.write("- `test_tree_utils.py` - Tree utility tests\n")
        f.write("\n")

        f.write("---\n\n")
        f.write("*Generated automatically by Query Optimizer Test Suite*\n")

    print(f"\n[OK] Main test report: {report_file}")


def create_test_suite(modules=None):
    """Create a test suite with specified test modules.

    Args:
        modules: List of module names to include. If None, includes all modules.

    Returns:
        unittest.TestSuite: The test suite with selected modules.
    """
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    if modules is None:
        # Add all test modules
        modules = ['tokenizer', 'parser', 'optimizer', 'rules', 'tree-utils']

    # Load tests from selected modules
    for module_name in modules:
        if module_name in TEST_MODULES:
            module = TEST_MODULES[module_name]
            tests = loader.loadTestsFromModule(module)
            suite.addTests(tests)

    return suite


class CustomTextTestResult(unittest.TextTestResult):
    """Custom test result class that adds [OK]/[ERROR] prefix to test output."""

    def startTest(self, test):
        """Called when test starts."""
        unittest.TestResult.startTest(self, test)  # Skip parent's output
        if self.showAll:
            self.stream.write("[ OK ] ")
            self.stream.write(self.getDescription(test))
            self.stream.write(" ... ")
            self.stream.flush()

    def addSuccess(self, test):
        """Called when test succeeds."""
        unittest.TestResult.addSuccess(self, test)  # Skip parent's output
        if self.showAll:
            self.stream.write("ok\n")
            self.stream.flush()
        elif self.dots:
            self.stream.write('.')
            self.stream.flush()

    def addError(self, test, err):
        """Called when test has an error."""
        # First overwrite the [OK] with [ERROR]
        if self.showAll:
            self.stream.write("\r[ERROR] ")
            self.stream.write(self.getDescription(test))
            self.stream.write(" ... ERROR\n")
            self.stream.flush()
        elif self.dots:
            self.stream.write('E')
            self.stream.flush()
        unittest.TestResult.addError(self, test, err)

    def addFailure(self, test, err):
        """Called when test fails."""
        # First overwrite the [OK] with [FAIL]
        if self.showAll:
            self.stream.write("\r[FAIL] ")
            self.stream.write(self.getDescription(test))
            self.stream.write(" ... FAIL\n")
            self.stream.flush()
        elif self.dots:
            self.stream.write('F')
            self.stream.flush()
        unittest.TestResult.addFailure(self, test, err)

    def addSkip(self, test, reason):
        """Called when test is skipped."""
        # First overwrite the [OK] with [SKIP]
        if self.showAll:
            self.stream.write("\r[SKIP] ")
            self.stream.write(self.getDescription(test))
            self.stream.write(f" ... skipped '{reason}'\n")
            self.stream.flush()
        elif self.dots:
            self.stream.write('s')
            self.stream.flush()
        unittest.TestResult.addSkip(self, test, reason)


class CustomTextTestRunner(unittest.TextTestRunner):
    """Custom test runner that uses CustomTextTestResult."""

    resultclass = CustomTextTestResult


def run_tests_with_report(modules=None, verbosity=2, show_trees=False, output_dir='Query_Optimizer/test_output'):
    """Run tests and generate reports.

    Args:
        modules: List of module names to test. If None, tests all modules.
        verbosity: Test output verbosity level.
        show_trees: Whether to output tree structures in parser tests.
        output_dir: Directory for output files.

    Returns:
        unittest.TestResult: The test results.
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Create test suite
    suite = create_test_suite(modules)

    # Run tests with custom result tracking
    runner = CustomTextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    # Generate reports
    generate_markdown_report(result, modules, output_dir)
    generate_module_reports(result, modules or list(
        TEST_MODULES.keys()), output_dir, show_trees)

    return result


if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Query Optimizer Test Suite',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python Query_Optimizer/UnitTest.py                    # Run all tests
  python Query_Optimizer/UnitTest.py --tokenizer        # Run only tokenizer tests
  python Query_Optimizer/UnitTest.py --parser           # Run only parser tests
  python Query_Optimizer/UnitTest.py --parser --show-trees  # Parser tests with tree output
  python Query_Optimizer/UnitTest.py --optimizer --rules     # Run optimizer and rules tests
  python Query_Optimizer/UnitTest.py -v                 # Verbose output
        """
    )

    # Test module selection
    parser.add_argument('--tokenizer', action='store_true',
                        help='Run tokenizer tests')
    parser.add_argument('--parser', action='store_true',
                        help='Run parser tests')
    parser.add_argument('--optimizer', action='store_true',
                        help='Run optimizer tests')
    parser.add_argument('--rules', action='store_true',
                        help='Run optimization rules tests')
    parser.add_argument('--tree-utils', action='store_true',
                        help='Run tree utilities tests')

    # Output options
    parser.add_argument('--show-trees', action='store_true',
                        help='Show parse tree visualizations in parser output')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose test output')
    parser.add_argument('--output-dir', default='Query_Optimizer/test_output',
                        help='Directory for output files (default: Query_Optimizer/test_output)')

    args = parser.parse_args()

    # Determine which modules to test
    selected_modules = []
    if args.tokenizer:
        selected_modules.append('tokenizer')
    if args.parser:
        selected_modules.append('parser')
    if args.optimizer:
        selected_modules.append('optimizer')
    if args.rules:
        selected_modules.append('rules')
    if args.tree_utils:
        selected_modules.append('tree-utils')

    # If no modules specified, run all
    if not selected_modules:
        selected_modules = None
        module_names = "all modules"
    else:
        module_names = ", ".join(selected_modules)

    # Print header
    print("=" * 70)
    print("Query Optimizer Test Suite")
    print("=" * 70)
    print(f"Testing: {module_names}")
    print(f"Output directory: {args.output_dir}")
    if args.show_trees:
        print("Tree visualization: ENABLED")
    print("=" * 70)
    print()

    # Run tests with options
    verbosity = 2 if args.verbose else 1
    result = run_tests_with_report(
        modules=selected_modules,
        verbosity=verbosity,
        show_trees=args.show_trees,
        output_dir=args.output_dir
    )

    # Print summary
    print()
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Total: {result.testsRun}")
    print(
        f"Passed: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failed: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.testsRun > 0:
        success_rate = ((result.testsRun - len(result.failures) -
                        len(result.errors)) / result.testsRun) * 100
        print(f"Success Rate: {success_rate:.2f}%")

    print("=" * 70)

    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)
