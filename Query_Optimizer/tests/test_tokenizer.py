"""
Tests for SQL Tokenizer
"""
import unittest
from typing import List, Tuple

from Query_Optimizer.lib.helpers.tokenizer import SQLTokenizer, SQLToken


class TestSQLTokenizer(unittest.TestCase):
    """Test suite for SQL tokenizer functionality."""

    def _get_token_snapshot(self, tokens: List[SQLToken], length: int = None) -> List[Tuple[str, str]]:
        """Helper to extract (type, value) pairs from tokens."""
        if length is None:
            length = len(tokens)
        return [(tokens[i].type, tokens[i].value) for i in range(min(length, len(tokens)))]

    def test_simple_select_query(self):
        """Test tokenization of a basic SELECT query."""
        query = "SELECT * FROM users"
        tokens = SQLTokenizer(query).tokenize()
        snapshot = self._get_token_snapshot(tokens, 4)

        expected = [
            ('KEYWORD', 'SELECT'),
            ('OPERATOR', '*'),
            ('KEYWORD', 'FROM'),
            ('IDENTIFIER', 'users'),
        ]
        self.assertEqual(snapshot, expected)

    def test_query_with_where_clause(self):
        """Test tokenization of SELECT with WHERE clause."""
        query = "SELECT name, age FROM users WHERE age >= 18"
        tokens = SQLTokenizer(query).tokenize()

        # Verify essential tokens are present
        token_values = [t.value for t in tokens]
        self.assertIn('SELECT', token_values)
        self.assertIn('name', token_values)
        self.assertIn('age', token_values)
        self.assertIn('WHERE', token_values)
        self.assertIn('>=', token_values)
        self.assertIn('18', token_values)

    def test_string_literals(self):
        """Test tokenization handles string literals correctly."""
        query = "SELECT 'ACTIVE' as status FROM users"
        tokens = SQLTokenizer(query).tokenize()

        string_tokens = [t for t in tokens if t.type == 'STRING']
        self.assertEqual(len(string_tokens), 1)
        self.assertEqual(string_tokens[0].value, 'ACTIVE')

    def test_inline_comments_ignored(self):
        """Test that inline comments are properly ignored."""
        query = """
        SELECT name, 'ACTIVE' as status -- inline comment
        FROM users
        WHERE age >= 18
        """.strip()

        tokens = SQLTokenizer(query).tokenize()
        token_values = [t.value for t in tokens]

        # Comments should not appear in tokens
        self.assertNotIn('--', token_values)
        self.assertNotIn('inline', token_values)
        self.assertNotIn('comment', token_values)

        # But actual keywords should be present
        self.assertIn('SELECT', token_values)
        self.assertIn('name', token_values)

    def test_block_comments_ignored(self):
        """Test that block comments are properly ignored."""
        query = """
        SELECT name
        FROM users /* this is a block comment */
        WHERE id = 1
        """.strip()

        tokens = SQLTokenizer(query).tokenize()
        token_values = [t.value for t in tokens]

        # Block comment content should not appear
        self.assertNotIn('this', token_values)
        self.assertNotIn('block', token_values)

    def test_multiple_operators(self):
        """Test tokenization of various SQL operators."""
        query = "SELECT * FROM users WHERE age >= 18 AND status = 'ACTIVE' OR balance > 100"
        tokens = SQLTokenizer(query).tokenize()

        operators = [t.value for t in tokens if t.type in [
            'OPERATOR', 'KEYWORD']]
        self.assertIn('>=', operators)
        self.assertIn('=', operators)
        self.assertIn('>', operators)
        self.assertIn('AND', operators)
        self.assertIn('OR', operators)

    def test_join_query(self):
        """Test tokenization of JOIN queries."""
        query = "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id"
        tokens = SQLTokenizer(query).tokenize()

        token_values = [t.value for t in tokens]
        self.assertIn('JOIN', token_values)
        self.assertIn('ON', token_values)
        self.assertIn('u', token_values)
        self.assertIn('o', token_values)

    def test_unclosed_string_raises_error(self):
        """Test that unclosed string literal raises ValueError."""
        bad_query = "SELECT 'oops"

        with self.assertRaises(ValueError) as context:
            SQLTokenizer(bad_query).tokenize()

        # Check for either error message variant
        error_msg = str(context.exception)
        self.assertTrue('Unterminated' in error_msg or 'Unclosed' in error_msg)

    def test_empty_query(self):
        """Test tokenization of empty or whitespace-only query."""
        query = "   "
        tokens = SQLTokenizer(query).tokenize()

        # Should return EOF token or empty list
        self.assertTrue(len(tokens) <= 1)

    def test_numeric_literals(self):
        """Test tokenization of numeric values."""
        query = "SELECT * FROM users WHERE age = 25 AND balance > 1000.50"
        tokens = SQLTokenizer(query).tokenize()

        numeric_tokens = [t for t in tokens if t.type == 'NUMBER']
        numeric_values = [t.value for t in numeric_tokens]

        self.assertIn('25', numeric_values)
        self.assertIn('1000.50', numeric_values)

    def test_punctuation(self):
        """Test tokenization of punctuation marks."""
        query = "SELECT name, age, status FROM users"
        tokens = SQLTokenizer(query).tokenize()

        punctuation = [t for t in tokens if t.type == 'PUNCTUATION']
        self.assertEqual(len(punctuation), 2)  # Two commas
        self.assertTrue(all(t.value == ',' for t in punctuation))

    def test_complex_query(self):
        """Test tokenization of a complex query with multiple clauses."""
        query = """
        SELECT u.name, COUNT(o.id) as order_count
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        WHERE u.status = 'ACTIVE'
        GROUP BY u.name
        HAVING COUNT(o.id) > 5
        ORDER BY order_count DESC
        """.strip()

        tokens = SQLTokenizer(query).tokenize()
        token_values = [t.value for t in tokens]
        token_values_upper = [t.value.upper() for t in tokens]

        # Verify all major keywords are present (case-insensitive)
        expected_keywords = ['SELECT', 'FROM', 'LEFT', 'JOIN', 'ON', 'WHERE',
                             'GROUP', 'BY', 'HAVING', 'ORDER', 'DESC']
        for keyword in expected_keywords:
            self.assertIn(keyword, token_values_upper,
                          f"Missing keyword: {keyword}")


if __name__ == '__main__':
    unittest.main()
