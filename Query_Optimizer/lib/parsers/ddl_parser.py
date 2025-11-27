"""
DDL Parser
Handles parsing of DDL statements: CREATE, DROP, and transaction commands.
"""

from globalsy.classes.query_tree import QueryTree
from globalsy.constants.query_types import QueryTypes
from .base_parser import BaseParser


class DDLParser(BaseParser):
    """Handles parsing of DDL and transaction statements"""

    def parse_create(self) -> QueryTree:
        """Parse CREATE TABLE statement"""
        self._expect_keyword(QueryTypes.CREATE)
        self._expect_keyword(QueryTypes.TABLE)

        # Parse table name
        if self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            raise ValueError(
                f"Expected table name, got '{self.current_token.value}'")
        table_name = self.current_token.value
        self._advance()

        table_node = QueryTree(type=QueryTypes.TABLE, val=table_name)

        # Parse column definitions
        self._expect_punctuation('(')
        columns_node = self._parse_column_definitions()
        self._expect_punctuation(')')

        return QueryTree(type=QueryTypes.CREATE_TABLE, val=QueryTypes.CREATE_TABLE, childs=[table_node, columns_node])

    def _parse_foreign_key_constraint(self) -> QueryTree:
        self._expect_keyword('FOREIGN')
        self._expect_keyword('KEY')

        self._expect_punctuation('(')

        local_col = self.current_token.value
        self._advance()
        self._expect_punctuation(')')

        self._expect_keyword('REFERENCES')

        ref_table = self.current_token.value
        self._advance()

        self._expect_punctuation('(')
        ref_col = self.current_token.value
        self._advance()
        self._expect_punctuation(')')

        # Buat node khusus untuk Foreign Key
        fk_node = QueryTree(type='FOREIGN_KEY_CONSTRAINT', val=local_col)
        fk_node.childs.append(
            QueryTree(type='REFERENCES_TABLE', val=ref_table))
        fk_node.childs.append(QueryTree(type='REFERENCES_COLUMN', val=ref_col))

        return fk_node

    def _parse_table_primary_key(self) -> QueryTree:
        """
        Mem-parsing: PRIMARY KEY (col1, col2, ...)
        Kita asumsikan token 'PRIMARY' sudah di-match.
        """
        self._expect_keyword('PRIMARY')
        self._expect_keyword('KEY')

        self._expect_punctuation('(')

        pk_cols = []
        while True:
            col_name = self.current_token.value
            self._advance()
            pk_cols.append(QueryTree(type='IDENTIFIER', val=col_name))

            if self._match_punctuation(','):
                self._advance()
            elif self.current_token.value == ')':
                break
            else:
                raise ValueError(
                    "Expected ',' or ')' in PRIMARY KEY definition")

        self._expect_punctuation(')')

        return QueryTree(type='PRIMARY_KEY_CONSTRAINT', val='TABLE_PK', childs=pk_cols)

    def _parse_column_definitions(self) -> QueryTree:
        """Parse column definitions in CREATE TABLE"""
        columns = []

        while True:
            if self._match_keyword('FOREIGN'):
                # Jika token-nya 'FOREIGN', panggil parser khusus FK
                fk_node = self._parse_foreign_key_constraint()
                columns.append(fk_node)

            elif self._match_keyword('PRIMARY'):
                # Jika token-nya 'PRIMARY', panggil parser khusus PK
                pk_node = self._parse_table_primary_key()
                columns.append(pk_node)

            elif self._match_keyword('CONSTRAINT'):
                raise NotImplementedError(
                    "Parsing 'CONSTRAINT' belum didukung")

            elif self.current_token.type == 'IDENTIFIER':
                col_name = self.current_token.value
                self._advance()

                if not self._match_keyword('INT') and not self._match_keyword('FLOAT') and \
                   not self._match_keyword('CHAR'):

                    raise ValueError(
                        f"Expected data type (INT, FLOAT, or CHAR) after column '{col_name}', got '{self.current_token.value}'")

                data_type = self.current_token.value
                self._advance()

                size = None
                if self._match_punctuation('('):
                    self._advance()
                    if self.current_token.type != 'NUMBER':
                        raise ValueError(
                            f"Expected size, got '{self.current_token.value}'")
                    size = self.current_token.value
                    self._advance()
                    self._expect_punctuation(')')

                constraints = []
                while self._match_keyword('PRIMARY') or self._match_keyword('UNIQUE') or self._match_keyword('NOT'):
                    if self._match_keyword('PRIMARY'):
                        self._advance()
                        self._expect_keyword('KEY')
                        constraints.append(
                            QueryTree(type=QueryTypes.CONSTRAINT, val='PRIMARY_KEY'))
                    elif self._match_keyword('UNIQUE'):
                        self._advance()
                        constraints.append(
                            QueryTree(type=QueryTypes.CONSTRAINT, val='UNIQUE'))
                    elif self._match_keyword('NOT'):
                        self._advance()
                        self._expect_keyword('NULL')
                        constraints.append(
                            QueryTree(type=QueryTypes.CONSTRAINT, val='NOT_NULL'))

                # Buat node
                type_val = data_type if not size else f"{data_type}({size})"
                type_node = QueryTree(type=QueryTypes.DATA_TYPE, val=type_val)

                childs = [type_node] + constraints
                col_def = QueryTree(type=QueryTypes.COLUMN_DEF,
                                    val=col_name, childs=childs)
                columns.append(col_def)

            else:
                # Jika bukan 'FOREIGN', 'PRIMARY', atau 'IDENTIFIER',
                # berarti sudah selesai (kemungkinan ')' )
                break

            # Cek koma pemisah
            if self._match_punctuation(','):
                self._advance()
            else:
                break

        return QueryTree(type=QueryTypes.COLUMN_DEFS, val='', childs=columns)

    def parse_drop(self) -> QueryTree:
        """Parse DROP TABLE statement"""
        self._expect_keyword(QueryTypes.DROP)
        self._expect_keyword(QueryTypes.TABLE)

        # Parse table name
        if self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            raise ValueError(
                f"Expected table name, got '{self.current_token.value}'")
        table_name = self.current_token.value
        self._advance()

        table_node = QueryTree(type=QueryTypes.TABLE, val=table_name)

        # Check for CASCADE or RESTRICT
        mode = None
        if self._match_keyword('CASCADE'):
            self._advance()
            mode = QueryTree(type=QueryTypes.DROP_MODE, val='CASCADE')
        elif self._match_keyword('RESTRICT'):
            self._advance()
            mode = QueryTree(type=QueryTypes.DROP_MODE, val='RESTRICT')

        childs = [table_node]
        if mode:
            childs.append(mode)

        return QueryTree(type=QueryTypes.DROP_TABLE, val=QueryTypes.DROP_TABLE, childs=childs)

    def parse_begin_transaction(self) -> QueryTree:
        """Parse BEGIN TRANSACTION"""
        self._expect_keyword('BEGIN')

        # TRANSACTION keyword is optional
        if self._match_keyword('TRANSACTION'):
            self._advance()

        return QueryTree(type=QueryTypes.BEGIN_TRANSACTION, val=QueryTypes.BEGIN_TRANSACTION)

    def parse_commit(self) -> QueryTree:
        """Parse COMMIT"""
        self._expect_keyword(QueryTypes.COMMIT)
        return QueryTree(type=QueryTypes.COMMIT, val=QueryTypes.COMMIT)
