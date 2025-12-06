from typing import List, Optional
import logging
from globalsy.classes.query_tree import QueryTree
from ..helpers.tokenizer import SQLToken
from .base_parser import BaseParser
from .query_parsers import QueryParsers
from .ddl_parser import DDLParser
from globalsy.constants.query_types import QueryTypes


class SQLParser(BaseParser):

    def __init__(self, tokens: List[SQLToken], logger: Optional[logging.Logger] = None):
        super().__init__(tokens, logger)
        self.query_parser = QueryParsers(tokens, logger)
        self.ddl_parser = DDLParser(tokens, logger)

    def parse(self) -> QueryTree:
        if not self.current_token or self.current_token.type == 'EOF':
            raise ValueError("Empty query")

        self._sync_parsers()

        if self._match_keyword(QueryTypes.SELECT):
            tree = self.query_parser.parse_select()
            self._update_from_query_parser()
        elif self._match_keyword(QueryTypes.UPDATE):
            tree = self.query_parser.parse_update()
            self._update_from_query_parser()
        elif self._match_keyword(QueryTypes.DELETE):
            tree = self.query_parser.parse_delete()
            self._update_from_query_parser()
        elif self._match_keyword(QueryTypes.INSERT):
            tree = self.query_parser.parse_insert()
            self._update_from_query_parser()
        elif self._match_keyword(QueryTypes.CREATE):
            tree = self.ddl_parser.parse_create()
            self._update_from_ddl_parser()
        elif self._match_keyword(QueryTypes.DROP):
            tree = self.ddl_parser.parse_drop()
            self._update_from_ddl_parser()
        elif self._match_keyword('BEGIN'):
            tree = self.ddl_parser.parse_begin_transaction()
            self._update_from_ddl_parser()
        elif self._match_keyword(QueryTypes.COMMIT):
            tree = self.ddl_parser.parse_commit()
            self._update_from_ddl_parser()
        else:
            raise ValueError(f"Unsupported query type: {self.current_token.value}")

        if self.current_token and self.current_token.value == ';':
            self._advance()

        if self.current_token and self.current_token.type != 'EOF':
            raise ValueError(f"Unexpected token after query: '{self.current_token.value}' at position {self.current_token.position}")

        return tree

    def _sync_parsers(self):
        self.query_parser.position = self.position
        self.query_parser.current_token = self.current_token
        self.ddl_parser.position = self.position
        self.ddl_parser.current_token = self.current_token

    def _update_from_query_parser(self):
        self.position = self.query_parser.position
        self.current_token = self.query_parser.current_token

    def _update_from_ddl_parser(self):
        self.position = self.ddl_parser.position
        self.current_token = self.ddl_parser.current_token
