"""
DDL Parser
Handles parsing of DDL statements: CREATE, DROP, and transaction commands.
"""

from ...types import QueryTree
from .base_parser import BaseParser


class DDLParser(BaseParser):
    """Handles parsing of DDL and transaction statements"""

    def parse_create(self) -> QueryTree:
        """Parse CREATE TABLE statement"""
        self._expect_keyword('CREATE')
        self._expect_keyword('TABLE')

        # Parse table name
        if self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            raise ValueError(
                f"Expected table name, got '{self.current_token.value}'")
        table_name = self.current_token.value
        self._advance()

        table_node = QueryTree(type='TABLE', val=table_name)

        # Parse column definitions
        self._expect_punctuation('(')
        columns_node = self._parse_column_definitions()
        self._expect_punctuation(')')

        return QueryTree(type='CREATE_TABLE', val='CREATE_TABLE', childs=[table_node, columns_node])

    def _parse_column_definitions(self) -> QueryTree:
        """Parse column definitions in CREATE TABLE"""
        columns = []

        while True:
            # Parse column name
            if self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                break  # Might be a constraint

            col_name = self.current_token.value
            self._advance()

            # Parse data type
            if not self._match_keyword('INTEGER') and not self._match_keyword('INT') and \
               not self._match_keyword('FLOAT') and not self._match_keyword('CHAR') and \
               not self._match_keyword('VARCHAR') and not self._match_keyword('TEXT') and \
               not self._match_keyword('DATE') and not self._match_keyword('TIMESTAMP'):
                # Check if it's a constraint keyword
                if self._match_keyword('PRIMARY') or self._match_keyword('FOREIGN') or \
                   self._match_keyword('CONSTRAINT'):
                    # This is a table constraint, not a column definition
                    # For now, we'll skip constraint parsing
                    break
                raise ValueError(
                    f"Expected data type, got '{self.current_token.value}'")

            data_type = self.current_token.value
            self._advance()

            # Parse size for CHAR/VARCHAR
            size = None
            if self._match_punctuation('('):
                self._advance()
                if self.current_token.type != 'NUMBER':
                    raise ValueError(
                        f"Expected size, got '{self.current_token.value}'")
                size = self.current_token.value
                self._advance()
                self._expect_punctuation(')')

            # Parse column constraints (PRIMARY KEY, etc.)
            constraints = []
            while self._match_keyword('PRIMARY') or self._match_keyword('FOREIGN') or \
                    self._match_keyword('UNIQUE') or self._match_keyword('NOT'):
                if self._match_keyword('PRIMARY'):
                    self._advance()
                    self._expect_keyword('KEY')
                    constraints.append(
                        QueryTree(type='CONSTRAINT', val='PRIMARY_KEY'))
                elif self._match_keyword('UNIQUE'):
                    self._advance()
                    constraints.append(
                        QueryTree(type='CONSTRAINT', val='UNIQUE'))
                elif self._match_keyword('NOT'):
                    self._advance()
                    self._expect_keyword('NULL')
                    constraints.append(
                        QueryTree(type='CONSTRAINT', val='NOT_NULL'))
                elif self._match_keyword('FOREIGN'):
                    # Skip FOREIGN KEY parsing for now
                    break

            type_val = data_type if not size else f"{data_type}({size})"
            type_node = QueryTree(type='DATA_TYPE', val=type_val)

            childs = [type_node] + constraints
            col_def = QueryTree(type='COLUMN_DEF', val=col_name, childs=childs)
            columns.append(col_def)

            if self._match_punctuation(','):
                self._advance()
            else:
                break

        return QueryTree(type='COLUMN_DEFS', val='', childs=columns)

    def parse_drop(self) -> QueryTree:
        """Parse DROP TABLE statement"""
        self._expect_keyword('DROP')
        self._expect_keyword('TABLE')

        # Parse table name
        if self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            raise ValueError(
                f"Expected table name, got '{self.current_token.value}'")
        table_name = self.current_token.value
        self._advance()

        table_node = QueryTree(type='TABLE', val=table_name)

        # Check for CASCADE or RESTRICT
        mode = None
        if self._match_keyword('CASCADE'):
            self._advance()
            mode = QueryTree(type='DROP_MODE', val='CASCADE')
        elif self._match_keyword('RESTRICT'):
            self._advance()
            mode = QueryTree(type='DROP_MODE', val='RESTRICT')

        childs = [table_node]
        if mode:
            childs.append(mode)

        return QueryTree(type='DROP_TABLE', val='DROP_TABLE', childs=childs)

    def parse_begin_transaction(self) -> QueryTree:
        """Parse BEGIN TRANSACTION"""
        self._expect_keyword('BEGIN')

        # TRANSACTION keyword is optional
        if self._match_keyword('TRANSACTION'):
            self._advance()

        return QueryTree(type='BEGIN_TRANSACTION', val='BEGIN_TRANSACTION')

    def parse_commit(self) -> QueryTree:
        """Parse COMMIT"""
        self._expect_keyword('COMMIT')
        return QueryTree(type='COMMIT', val='COMMIT')
