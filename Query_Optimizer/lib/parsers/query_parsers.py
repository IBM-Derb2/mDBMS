"""
Query Parsers
Handles parsing of DML queries: SELECT, UPDATE, DELETE, INSERT.
"""

from ...query_types import QueryTree
from .base_parser import BaseParser
from .expression_parser import ExpressionParser


class QueryParsers(BaseParser):
    """Handles parsing of DML queries"""

    def __init__(self, tokens, logger=None):
        super().__init__(tokens, logger)
        self.expr_parser = ExpressionParser(tokens, logger)
        # Keep expression parser in sync
        self.expr_parser.position = self.position
        self.expr_parser.current_token = self.current_token

    def _sync_expression_parser(self):
        """Keep expression parser in sync with current position"""
        self.expr_parser.position = self.position
        self.expr_parser.current_token = self.current_token

    def _advance_both(self):
        """Advance both parsers"""
        self._advance()
        self._sync_expression_parser()

    def parse_select(self) -> QueryTree:
        """Parse SELECT statement"""
        self._expect_keyword('SELECT')

        # Parse columns
        columns_node = self._parse_select_columns()

        # Parse FROM clause
        from_node = None
        if self._match_keyword('FROM'):
            from_node = self._parse_from_clause()

        # Parse WHERE clause
        where_node = None
        if self._match_keyword('WHERE'):
            where_node = self._parse_where_clause()

        # Parse ORDER BY clause
        order_by_node = None
        if self._match_keyword('ORDER'):
            order_by_node = self._parse_order_by_clause()

        # Parse LIMIT clause
        limit_node = None
        if self._match_keyword('LIMIT'):
            limit_node = self._parse_limit_clause()

        # Build SELECT tree
        childs = [columns_node]
        if from_node:
            childs.append(from_node)
        if where_node:
            childs.append(where_node)
        if order_by_node:
            childs.append(order_by_node)
        if limit_node:
            childs.append(limit_node)

        return QueryTree(type='SELECT', val='SELECT', childs=childs)

    def _parse_select_columns(self) -> QueryTree:
        """Parse column list in SELECT"""
        columns = []

        while True:
            # Check for * (all columns)
            if not self.current_token:
                raise ValueError(
                    "Unexpected end of input while parsing SELECT column list")
            if self.current_token.value == '*':
                columns.append(QueryTree(type='COLUMN', val='*'))
                self._advance()
            else:
                # Parse column expression
                self._sync_expression_parser()
                col_expr = self.expr_parser.parse_expression()
                self.position = self.expr_parser.position
                self.current_token = self.expr_parser.current_token

                # Check for AS alias
                if self._match_keyword('AS'):
                    self._advance()
                    if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                        bad = self.current_token.value if self.current_token else 'EOF'
                        raise ValueError(
                            f"Expected alias name, got '{bad}'")
                    alias = self.current_token.value
                    self._advance()
                    col_expr = QueryTree(
                        type='ALIAS', val=alias, childs=[col_expr])

                columns.append(col_expr)

            # Check for comma (more columns)
            if self._match_punctuation(','):
                self._advance()
            else:
                break

        return QueryTree(type='COLUMNS', val='', childs=columns)

    def _parse_from_clause(self) -> QueryTree:
        """Parse FROM clause with tables and joins"""
        self._expect_keyword('FROM')

        # Parse first table
        tables = [self._parse_table_reference()]

        # Parse additional tables (comma-separated) or joins
        while True:
            if self._match_punctuation(','):
                self._advance()
                tables.append(self._parse_table_reference())
            elif self._match_keyword('JOIN') or self._match_keyword('INNER') or \
                    self._match_keyword('NATURAL'):
                tables.append(self._parse_join())
            elif self.current_token and self.current_token.type == 'IDENTIFIER' and \
                    self.current_token.value.upper() in ('LEFT', 'RIGHT', 'FULL', 'CROSS', 'OUTER'):
                raise ValueError(
                    f"Unsupported JOIN type: {self.current_token.value.upper()}")
            else:
                break

        return QueryTree(type='FROM', val='', childs=tables)

    def _parse_table_reference(self) -> QueryTree:
        """Parse a table reference with optional alias (supports schema.table syntax)"""
        if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            bad = self.current_token.value if self.current_token else 'EOF'
            raise ValueError(
                f"Expected table name, got '{bad}'")

        table_name = self.current_token.value
        self._advance()

        # Check for schema.table syntax
        if self._match_punctuation('.'):
            self._advance()  # Skip the dot
            if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(
                    f"Expected table name after schema, got '{bad}'")
            # Combine schema and table name
            table_name = table_name + '.' + self.current_token.value
            self._advance()

        table_node = QueryTree(type='TABLE', val=table_name)

        # Check for AS alias
        if self._match_keyword('AS'):
            self._advance()
            if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(
                    f"Expected alias name, got '{bad}'")
            alias = self.current_token.value
            self._advance()
            return QueryTree(type='ALIAS', val=alias, childs=[table_node])
        # Check for implicit alias (no AS keyword)
        elif self.current_token and self.current_token.type == 'IDENTIFIER' and \
                not self._match_keyword('WHERE') and \
                not self._match_keyword('JOIN') and \
                not self._match_punctuation(',') and \
                not self._match_keyword('ORDER') and \
                not self._match_keyword('LIMIT'):
            alias = self.current_token.value
            # Reject unsupported JOIN keywords used as aliases
            if alias.upper() in ('LEFT', 'RIGHT', 'FULL', 'CROSS', 'OUTER'):
                raise ValueError(f"Unsupported JOIN type: {alias.upper()}")
            self._advance()
            return QueryTree(type='ALIAS', val=alias, childs=[table_node])

        return table_node

    def _parse_join(self) -> QueryTree:
        """Parse JOIN clause - supports only INNER JOIN (with ON) and NATURAL JOIN"""
        join_type = 'INNER'
        start_pos = self.position

        # Check for NATURAL JOIN
        if self._match_keyword('NATURAL'):
            self._advance()
            join_type = 'NATURAL'
        # Check for explicit INNER keyword (optional)
        elif self._match_keyword('INNER'):
            self._advance()
            join_type = 'INNER'

        self._expect_keyword('JOIN')

        # Parse table reference
        table_node = self._parse_table_reference()

        # Parse ON condition (required for INNER JOIN, not allowed for NATURAL JOIN)
        condition_node = None
        if join_type == 'NATURAL':
            # NATURAL JOIN doesn't use ON clause
            pass
        else:
            # INNER JOIN requires ON clause
            self._expect_keyword('ON')
            self._sync_expression_parser()
            condition_node = self.expr_parser.parse_expression()
            self.position = self.expr_parser.position
            self.current_token = self.expr_parser.current_token

        childs = [table_node]
        if condition_node:
            childs.append(condition_node)

        return QueryTree(type='JOIN', val=join_type, childs=childs)

    def _parse_where_clause(self) -> QueryTree:
        """Parse WHERE clause"""
        self._expect_keyword('WHERE')
        self._sync_expression_parser()
        condition = self.expr_parser.parse_expression()
        self.position = self.expr_parser.position
        self.current_token = self.expr_parser.current_token
        return QueryTree(type='WHERE', val='', childs=[condition])

    def _parse_order_by_clause(self) -> QueryTree:
        """Parse ORDER BY clause"""
        self._expect_keyword('ORDER')
        self._expect_keyword('BY')
        start_pos = self.position

        columns = []
        directions = []
        while True:
            # Parse column token (optionally qualified e.g., alias.column)
            if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(
                    f"Expected column name in ORDER BY, got '{bad}'")
            column_name = self.current_token.value
            self._advance()
            if self._match_punctuation('.'):
                self._advance()
                if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                    bad = self.current_token.value if self.current_token else 'EOF'
                    raise ValueError(
                        f"Expected column name after '.', got '{bad}'")
                column_name = column_name + '.' + self.current_token.value
                self._advance()
            direction = 'ASC'
            if self._match_keyword('ASC'):
                self._advance()
            elif self._match_keyword('DESC'):
                direction = 'DESC'
                self._advance()
            columns.append(QueryTree(type='COLUMN', val=column_name))
            directions.append(direction)
            if self._match_punctuation(','):
                self._advance()
                continue
            else:
                break
        order_children = []
        for col, dirn in zip(columns, directions):
            order_children.append(
                QueryTree(type='ORDER_ITEM', val=dirn, childs=[col]))
        return QueryTree(type='ORDER_BY', val='ORDER_BY', childs=order_children)

    def _parse_limit_clause(self) -> QueryTree:
        """Parse LIMIT clause"""
        self._expect_keyword('LIMIT')
        if not self.current_token or self.current_token.type != 'NUMBER':
            bad = self.current_token.value if self.current_token else 'EOF'
            raise ValueError(
                f"Expected number in LIMIT, got '{bad}'")
        limit_val = self.current_token.value
        self._advance()

        return QueryTree(type='LIMIT', val=limit_val)

    def parse_update(self) -> QueryTree:
        """Parse UPDATE statement"""
        self._expect_keyword('UPDATE')
        if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            bad = self.current_token.value if self.current_token else 'EOF'
            raise ValueError(
                f"Expected table name, got '{bad}'")
        table_name = self.current_token.value
        self._advance()

        table_node = QueryTree(type='TABLE', val=table_name)

        # Parse SET clause
        self._expect_keyword('SET')
        set_node = self._parse_set_clause()

        # Parse WHERE clause
        where_node = None
        if self._match_keyword('WHERE'):
            where_node = self._parse_where_clause()

        childs = [table_node, set_node]
        if where_node:
            childs.append(where_node)

        return QueryTree(type='UPDATE', val='UPDATE', childs=childs)

    def _parse_set_clause(self) -> QueryTree:
        """Parse SET clause in UPDATE"""
        assignments = []

        while True:
            # Parse column = expression
            if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(
                    f"Expected column name in SET, got '{bad}'")
            column = self.current_token.value
            self._advance()

            # Expect = operator
            if not self._match_operator('='):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(
                    f"Expected '=' in SET clause, got '{bad}'")
            self._advance()

            self._sync_expression_parser()
            value_expr = self.expr_parser.parse_expression()
            self.position = self.expr_parser.position
            self.current_token = self.expr_parser.current_token

            col_node = QueryTree(type='COLUMN', val=column)
            assignment = QueryTree(type='ASSIGNMENT', val='=', childs=[
                                   col_node, value_expr])
            assignments.append(assignment)

            # Check for comma (more assignments)
            if self._match_punctuation(','):
                self._advance()
            else:
                break

        return QueryTree(type='SET', val='', childs=assignments)

    def parse_delete(self) -> QueryTree:
        """Parse DELETE statement"""
        self._expect_keyword('DELETE')
        self._expect_keyword('FROM')
        if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            bad = self.current_token.value if self.current_token else 'EOF'
            raise ValueError(
                f"Expected table name, got '{bad}'")
        table_name = self.current_token.value
        self._advance()

        table_node = QueryTree(type='TABLE', val=table_name)

        # Parse WHERE clause
        where_node = None
        if self._match_keyword('WHERE'):
            where_node = self._parse_where_clause()

        childs = [table_node]
        if where_node:
            childs.append(where_node)

        return QueryTree(type='DELETE', val='DELETE', childs=childs)

    def parse_insert(self) -> QueryTree:
        """Parse INSERT statement"""
        self._expect_keyword('INSERT')
        self._expect_keyword('INTO')
        if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            bad = self.current_token.value if self.current_token else 'EOF'
            raise ValueError(
                f"Expected table name, got '{bad}'")
        table_name = self.current_token.value
        self._advance()

        table_node = QueryTree(type='TABLE', val=table_name)

        # Parse column list (optional)
        columns_node = None
        if self._match_punctuation('('):
            columns_node = self._parse_column_list()

        # Parse VALUES
        self._expect_keyword('VALUES')
        values_node = self._parse_values_clause()

        childs = [table_node]
        if columns_node:
            childs.append(columns_node)
        childs.append(values_node)

        return QueryTree(type='INSERT', val='INSERT', childs=childs)

    def _parse_column_list(self) -> QueryTree:
        """Parse column list in INSERT"""
        self._expect_punctuation('(')

        columns = []
        while True:
            if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(
                    f"Expected column name, got '{bad}'")
            columns.append(
                QueryTree(type='COLUMN', val=self.current_token.value))
            self._advance()

            if self._match_punctuation(','):
                self._advance()
            else:
                break

        self._expect_punctuation(')')

        return QueryTree(type='COLUMNS', val='', childs=columns)

    def _parse_values_clause(self) -> QueryTree:
        """Parse VALUES clause"""
        self._expect_punctuation('(')

        values = []
        while True:
            self._sync_expression_parser()
            value_expr = self.expr_parser.parse_expression()
            self.position = self.expr_parser.position
            self.current_token = self.expr_parser.current_token
            values.append(value_expr)

            if self._match_punctuation(','):
                self._advance()
            else:
                break

        self._expect_punctuation(')')

        return QueryTree(type='VALUES', val='', childs=values)
