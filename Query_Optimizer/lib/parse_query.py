"""
SQL Query Parser - Main Module
Orchestrates all the specialized parsers to parse SQL queries into QueryTree structures.
"""

from typing import List, Optional
import logging
from ..types import ParsedQuery, QueryTree
from .helpers.tokenizer import SQLToken, SQLTokenizer
from .parsers.base_parser import BaseParser
from .parsers.expression_parser import ExpressionParser
from .parsers.query_parsers import QueryParsers
from .parsers.ddl_parser import DDLParser


class SQLParser(BaseParser):
    """Main SQL Parser that orchestrates all specialized parsers"""

    def __init__(self, tokens: List[SQLToken], logger: Optional[logging.Logger] = None):
        super().__init__(tokens, logger)

        # Initialize specialized parsers
        self.query_parser = QueryParsers(tokens, logger)
        self.ddl_parser = DDLParser(tokens, logger)

    def parse(self) -> QueryTree:
        """Parse the token stream into a QueryTree"""
        if not self.current_token or self.current_token.type == 'EOF':
            raise ValueError("Empty query")

        # Sync all parsers to current position
        self._sync_parsers()

        # Determine query type from first keyword and delegate to appropriate parser
        if self._match_keyword('SELECT'):
            tree = self.query_parser.parse_select()
            self._update_from_query_parser()
        elif self._match_keyword('UPDATE'):
            tree = self.query_parser.parse_update()
            self._update_from_query_parser()
        elif self._match_keyword('DELETE'):
            tree = self.query_parser.parse_delete()
            self._update_from_query_parser()
        elif self._match_keyword('INSERT'):
            tree = self.query_parser.parse_insert()
            self._update_from_query_parser()
        elif self._match_keyword('CREATE'):
            tree = self.ddl_parser.parse_create()
            self._update_from_ddl_parser()
        elif self._match_keyword('DROP'):
            tree = self.ddl_parser.parse_drop()
            self._update_from_ddl_parser()
        elif self._match_keyword('BEGIN'):
            tree = self.ddl_parser.parse_begin_transaction()
            self._update_from_ddl_parser()
        elif self._match_keyword('COMMIT'):
            tree = self.ddl_parser.parse_commit()
            self._update_from_ddl_parser()
        else:
            raise ValueError(
                f"Unsupported query type: {self.current_token.value}")
        
        if self.current_token and self.current_token.value == ';':
            self._advance()

        # Verify we've consumed all tokens (except EOF)
        if self.current_token and self.current_token.type != 'EOF':
            raise ValueError(
                f"Unexpected token after query: '{self.current_token.value}' at position {self.current_token.position}"
            )

        return tree

    def _sync_parsers(self):
        """Synchronize all parsers to current position"""
        self.query_parser.position = self.position
        self.query_parser.current_token = self.current_token
        self.ddl_parser.position = self.position
        self.ddl_parser.current_token = self.current_token

    def _update_from_query_parser(self):
        """Update position from query parser"""
        self.position = self.query_parser.position
        self.current_token = self.query_parser.current_token

    def _update_from_ddl_parser(self):
        """Update position from DDL parser"""
        self.position = self.ddl_parser.position
        self.current_token = self.ddl_parser.current_token


def internal_parse_query(query: str, logger: Optional[logging.Logger] = None) -> ParsedQuery:
    """
    Menerima query dalam bentuk string dan mengubahnya menjadi object yang merepresentasikan query yang telah di-parse.
    Implementasi internal dari objek parsed query sepenuhnya diserahkan kepada masing - masing kelompok.
    """
    if not query or not query.strip():
        raise ValueError("Query string cannot be empty")

    # Tokenize
    tokenizer = SQLTokenizer(query, logger=logger)
    tokens = tokenizer.tokenize()

    # Parse
    parser = SQLParser(tokens, logger=logger)
    query_tree = parser.parse()

    # Create ParsedQuery
    parsed_query = ParsedQuery(query_tree=query_tree, query=query)

    return parsed_query
