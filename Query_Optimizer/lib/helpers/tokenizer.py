"""
SQL Tokenizer
Breaks SQL query strings into tokens for parsing.
"""

from typing import List, Optional
from globalsy.constants.query_types import QueryTypes
import logging


class SQLToken:
    """Represents a single SQL token"""

    def __init__(self, type: str, value: str, position: int):
        self.type = type  # KEYWORD, IDENTIFIER, OPERATOR, NUMBER, STRING, PUNCTUATION, EOF
        self.value = value
        self.position = position

    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"


class SQLTokenizer:
    """Tokenizes SQL query strings"""

    KEYWORDS = {
        QueryTypes.SELECT, QueryTypes.FROM, QueryTypes.WHERE,
        QueryTypes.INSERT, QueryTypes.INTO, QueryTypes.VALUES,
        QueryTypes.UPDATE,
        QueryTypes.DELETE, QueryTypes.SET,

        QueryTypes.CREATE, QueryTypes.TABLE, QueryTypes.DROP,

        QueryTypes.JOIN,
        # 'INNER' and 'NATURAL' are JOIN modifiers and do not map to separate QueryTypes constants.
        # The parser stores the join type inside the join node (QueryTypes.JOIN) via the "val" property
        # so we include these strings so the tokenizer recognizes them as keywords (KEYWORD tokens),
        # and the parser can call _match_keyword('INNER') or _match_keyword('NATURAL') as needed.
        'INNER', 'NATURAL',
        QueryTypes.ON, QueryTypes.AS,

        # Logical operators and expression keywords (AND/OR/NOT/IN/LIKE/BETWEEN) are represented
        # as OPERATOR nodes semantically, but we list them here as strings so:
        # - Tokenizer recognizes them as KEYWORD tokens (so _match_keyword works in parsers), and
        # - ExpressionParser uses _match_keyword to detect these keywords when parsing expressions
        #   (e.g., _match_keyword('IN') or _match_keyword('LIKE')).
        # This allows mixing both operator/token matching styles consistently in the parser code.
        'AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN',

        QueryTypes.ORDER, QueryTypes.BY, QueryTypes.ASC, QueryTypes.DESC, QueryTypes.LIMIT, QueryTypes.OFFSET,
        QueryTypes.GROUP, QueryTypes.HAVING, QueryTypes.DISTINCT, QueryTypes.ALL, QueryTypes.UNION, QueryTypes.INTERSECT, QueryTypes.EXCEPT,

        # Transaction control keywords: the tokenizer uses these strings so the DDL parser
        # (_expect_keyword('BEGIN') / _expect_keyword('COMMIT')) can detect them.
        # The parser will then emit a node type like QueryTypes.BEGIN_TRANSACTION or QueryTypes.COMMIT.
        'BEGIN', 'COMMIT', 'ROLLBACK', 'TRANSACTION',

        # DDL constraint keywords: 'PRIMARY', 'KEY', 'FOREIGN', 'REFERENCES', 'CONSTRAINT'
        # are used by the DDL parser to handle constraints, foreign keys, etc. They are not
        # represented as dedicated QueryTypes constants (e.g., PRIMARY/KEY), so we add them as
        # strings to ensure the tokenizer returns KEYWORD tokens and the parser can match them.
        'PRIMARY', 'KEY', 'FOREIGN', 'REFERENCES', 'CONSTRAINT',

        # Data types and constraint modifiers (INT/FLOAT/CHAR and NULL/DEFAULT/UNIQUE/CHECK/CASCADE/RESTRICT)
        # are not per se QueryType constants — the DDL parser interprets them and converts them into
        # QueryTypes.DATA_TYPE or appropriate constraint nodes while building column definitions. They
        # are included as strings so they become KEYWORD tokens and the parsing code can easily detect
        # types and modifiers using _match_keyword('INT'), _match_keyword('NULL'), etc.
        'INT', 'FLOAT', 'CHAR', 'VARCHAR',
        'NULL', 'DEFAULT', 'UNIQUE', 'CHECK', 'CASCADE', 'RESTRICT'
    }

    def __init__(self, query: str, logger: Optional[logging.Logger] = None):
        self.query = query
        self.position = 0
        self.tokens: List[SQLToken] = []
        self.logger = logger

    def tokenize(self) -> List[SQLToken]:
        """Tokenize the entire query"""
        while self.position < len(self.query):
            self._skip_whitespace()
            if self.position >= len(self.query):
                break

            # Skip comments
            if self._peek() == '-' and self._peek(1) == '-':
                self._skip_line_comment()
                continue
            if self._peek() == '/' and self._peek(1) == '*':
                self._skip_block_comment()
                continue

            token = self._next_token()
            if token:
                self.tokens.append(token)

        # Add EOF token
        self.tokens.append(SQLToken('EOF', '', self.position))
        return self.tokens

    def _peek(self, offset: int = 0) -> Optional[str]:
        """Peek at character at current position + offset"""
        pos = self.position + offset
        if pos < len(self.query):
            return self.query[pos]
        return None

    def _advance(self, count: int = 1) -> str:
        """Advance position and return the character(s)"""
        result = self.query[self.position:self.position + count]
        self.position += count
        return result

    def _skip_whitespace(self):
        """Skip whitespace characters"""
        while self.position < len(self.query) and self.query[self.position].isspace():
            self.position += 1

    def _skip_line_comment(self):
        """Skip -- style comments"""
        while self.position < len(self.query) and self.query[self.position] != '\n':
            self.position += 1

    def _skip_block_comment(self):
        """Skip /* */ style comments"""
        self.position += 2  # Skip /*
        while self.position < len(self.query) - 1:
            if self.query[self.position] == '*' and self.query[self.position + 1] == '/':
                self.position += 2
                break
            self.position += 1

    def _next_token(self) -> Optional[SQLToken]:
        """Extract the next token"""
        start_pos = self.position
        char = self._peek()

        if char is None:
            return None

        # String literals (single or double quotes)
        if char in ('"', "'"):
            return self._read_string(char)

        # Numbers (including negative numbers)
        if char.isdigit() or (char == '-' and self._peek(1) and self._peek(1).isdigit()):
            return self._read_number()

        # Identifiers and keywords
        if char.isalpha() or char == '_':
            return self._read_identifier()

        # Operators and punctuation
        if char in '+-*/%':
            self._advance()
            return SQLToken('OPERATOR', char, start_pos)

        # Comparison operators
        if char == '=':
            self._advance()
            return SQLToken('OPERATOR', '=', start_pos)

        if char == '<':
            self._advance()
            if self._peek() == '=':
                self._advance()
                return SQLToken('OPERATOR', '<=', start_pos)
            elif self._peek() == '>':
                self._advance()
                return SQLToken('OPERATOR', '<>', start_pos)
            else:
                return SQLToken('OPERATOR', '<', start_pos)

        if char == '>':
            self._advance()
            if self._peek() == '=':
                self._advance()
                return SQLToken('OPERATOR', '>=', start_pos)
            else:
                return SQLToken('OPERATOR', '>', start_pos)

        if char == '!':
            self._advance()
            if self._peek() == '=':
                self._advance()
                return SQLToken('OPERATOR', '!=', start_pos)

        # Punctuation
        if char in '(),;.':
            self._advance()
            return SQLToken('PUNCTUATION', char, start_pos)

        # Wildcards
        if char == '*':
            self._advance()
            return SQLToken('IDENTIFIER', '*', start_pos)

        # Unknown character - skip it
        self._advance()
        return None

    def _read_string(self, quote_char: str) -> SQLToken:
        """Read a string literal"""
        start_pos = self.position
        self._advance()  # Skip opening quote
        value = ''
        found_closing_quote = False

        while self.position < len(self.query):
            char = self._peek()
            if char == quote_char:
                # Check for escaped quote
                if self._peek(1) == quote_char:
                    value += quote_char
                    self._advance(2)
                else:
                    self._advance()  # Skip closing quote
                    found_closing_quote = True
                    break
            else:
                value += char
                self._advance()

        if not found_closing_quote:
            raise ValueError(
                f"Unclosed string literal starting at position {start_pos}")

        return SQLToken('STRING', value, start_pos)

    def _read_number(self) -> SQLToken:
        """Read a numeric literal (including negative numbers)"""
        start_pos = self.position
        value = ''
        has_dot = False

        # Handle negative sign
        if self._peek() == '-':
            value += '-'
            self._advance()

        while self.position < len(self.query):
            char = self._peek()
            if char.isdigit():
                value += char
                self._advance()
            elif char == '.' and not has_dot:
                has_dot = True
                value += char
                self._advance()
            else:
                break

        return SQLToken('NUMBER', value, start_pos)

    def _read_identifier(self) -> SQLToken:
        """Read an identifier or keyword"""
        start_pos = self.position
        value = ''

        while self.position < len(self.query):
            char = self._peek()
            if char and (char.isalnum() or char == '_'):
                value += char
                self._advance()
            else:
                break

        # Check if it's a keyword
        upper_value = value.upper()
        if upper_value in self.KEYWORDS:
            # Use QueryTypes constant if available
            qt_value = getattr(QueryTypes, upper_value, upper_value)
            return SQLToken('KEYWORD', qt_value, start_pos)

        return SQLToken('IDENTIFIER', value.lower(), start_pos)
