from globalsy.classes.query_tree import QueryTree
from globalsy.constants.query_types import QueryTypes
from globalsy.constants.query_operators import QueryOperators
from .base_parser import BaseParser
from .expression_parser import ExpressionParser


class QueryParsers(BaseParser):
    def __init__(self, tokens, logger=None):
        super().__init__(tokens, logger)
        self.expr_parser = ExpressionParser(tokens, logger)

    def parse_select(self) -> QueryTree:

        self._expect_keyword(QueryTypes.SELECT)
        columns = self._parse_select_columns_list()

        relation_tree = None
        if self._match_keyword(QueryTypes.FROM):
            relation_tree = self._parse_from_clause()

        if not relation_tree:
            # SELECT tanpa FROM
            return QueryTree(type=QueryTypes.PROJECTION, val=columns, childs=[])

        # parse WHERE clause (jadi SELECTION_STMT wrapping relation)
        if self._match_keyword(QueryTypes.WHERE):
            condition = self._parse_where_condition()
            relation_tree = QueryTree(type=QueryTypes.SELECTION_STMT, val=None, childs=[relation_tree, condition])

        # apply PROJECTION (SELECT columns)
        projection_tree = QueryTree(type=QueryTypes.PROJECTION, val=columns, childs=[relation_tree])

        # parse ORDER BY clause
        if self._match_keyword(QueryTypes.ORDER):
            order_by_node = self._parse_order_by_clause()
            projection_tree = QueryTree(type=QueryTypes.ORDER_BY, val=order_by_node.val, childs=[projection_tree] + order_by_node.childs)

        # parse LIMIT clause
        if self._match_keyword(QueryTypes.LIMIT):
            limit_node = self._parse_limit_clause()
            projection_tree = QueryTree(type=QueryTypes.LIMIT, val=limit_node.val, childs=[projection_tree])

        return projection_tree

    def _parse_select_columns_list(self) -> list:

        columns = []

        while True:
            if not self.current_token:
                raise ValueError("Unexpected end of input while parsing SELECT column list")

            if self.current_token.value == '*':
                columns.append('*')
                self._advance()
            else:
                self.expr_parser.position = self.position
                self.expr_parser.current_token = self.current_token
                col_expr = self.expr_parser.parse_expression()
                self.position = self.expr_parser.position
                self.current_token = self.expr_parser.current_token

                col_name = self._extract_expr_name(col_expr)

                if self._match_keyword('AS'):
                    self._advance()
                    if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                        bad = self.current_token.value if self.current_token else 'EOF'
                        raise ValueError(f"Expected alias name, got '{bad}'")
                    col_name = self.current_token.value
                    self._advance()

                columns.append(col_name)

            # cek koma (kolom selanjutnya)
            if self._match_punctuation(','):
                self._advance()
            else:
                break

        return columns if columns else ['*']

    def _extract_expr_name(self, expr_node: QueryTree) -> str:
        if expr_node.type == QueryTypes.COLUMN:
            return expr_node.val
        elif expr_node.val:
            return str(expr_node.val)
        return '*'

    def _parse_from_clause(self) -> QueryTree:
        self._expect_keyword(QueryTypes.FROM)

        table_name, alias_name = self._parse_table_name()
        table_node = QueryTree(type=QueryTypes.RELATION, val=table_name, childs=[])
        if alias_name:
            left = QueryTree(type=QueryTypes.ALIAS, val=alias_name, childs=[table_node], parent=None)
            table_node.parent = left
        else:
            left = table_node

        while True:
            if self._match_punctuation(','):
                self._advance()
                right_table, right_alias = self._parse_table_name()
                right_node = QueryTree(type=QueryTypes.RELATION, val=right_table, childs=[])
                if right_alias:
                    right = QueryTree(type=QueryTypes.ALIAS, val=right_alias, childs=[right_node], parent=None)
                    right_node.parent = right
                else:
                    right = right_node
                left = QueryTree(type=QueryTypes.CROSS_JOIN, val='', childs=[left, right])

            elif self._match_keyword('NATURAL'):
                self._advance()
                self._expect_keyword(QueryTypes.JOIN)
                right_table, right_alias = self._parse_table_name()
                right_node = QueryTree(type=QueryTypes.RELATION, val=right_table, childs=[])
                if right_alias:
                    right = QueryTree(type=QueryTypes.ALIAS, val=right_alias, childs=[right_node], parent=None)
                    right_node.parent = right
                else:
                    right = right_node
                left = QueryTree(type=QueryTypes.NATURAL_JOIN, val=None, childs=[left, right])

            elif self._match_keyword('JOIN') or self._match_keyword('INNER'):
                if self._match_keyword('INNER'):
                    self._advance()
                self._expect_keyword(QueryTypes.JOIN)
                right_table, right_alias = self._parse_table_name()
                right_node = QueryTree(type=QueryTypes.RELATION, val=right_table, childs=[])
                if right_alias:
                    right = QueryTree(type=QueryTypes.ALIAS, val=right_alias, childs=[right_node], parent=None)
                    right_node.parent = right
                else:
                    right = right_node

                self._expect_keyword(QueryTypes.ON)
                self.expr_parser.position = self.position
                self.expr_parser.current_token = self.current_token
                condition = self.expr_parser.parse_expression()
                self.position = self.expr_parser.position
                self.current_token = self.expr_parser.current_token

                if condition.type not in (QueryTypes.OPERATOR, 'AND', 'OR', 'NOT'):
                    raise ValueError(
                        f"JOIN ON condition must be a boolean expression, got {condition.type}")

                left = QueryTree(type=QueryTypes.THETA_JOIN, val='INNER', childs=[left, right, condition])

            elif self.current_token and self.current_token.type == 'IDENTIFIER' and \
                    self.current_token.value.upper() in ('LEFT', 'RIGHT', 'FULL', 'CROSS', 'OUTER'):
                raise ValueError(f"Unsupported JOIN type: {self.current_token.value.upper()}")
            else:
                break

        return left

    def _parse_table_name(self) -> tuple:
        if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            bad = self.current_token.value if self.current_token else 'EOF'
            raise ValueError(f"Expected table name, got '{bad}'")

        table_name = self.current_token.value
        self._advance()

        if self._match_punctuation('.'):
            self._advance()
            if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(f"Expected table name after schema, got '{bad}'")
            table_name = table_name + '.' + self.current_token.value
            self._advance()

        alias_name = None
        if self._match_keyword('AS'):
            self._advance()
            if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(f"Expected alias name after AS, got '{bad}'")
            alias_name = self.current_token.value
            self._advance()
        elif self.current_token and self.current_token.type == 'IDENTIFIER' and \
                not self._match_keyword('WHERE') and \
                not self._match_keyword('JOIN') and \
                not self._match_keyword('NATURAL') and \
                not self._match_punctuation(',') and \
                not self._match_keyword('ORDER') and \
                not self._match_keyword('LIMIT'):
            alias_name = self.current_token.value
            self._advance()

        return (table_name, alias_name)

    def _parse_where_condition(self):
        """Parse WHERE condition and return condition tree"""
        self._expect_keyword(QueryTypes.WHERE)
        self.expr_parser.position = self.position
        self.expr_parser.current_token = self.current_token
        condition = self.expr_parser.parse_expression()
        self.position = self.expr_parser.position
        self.current_token = self.expr_parser.current_token

        if condition.type not in (QueryTypes.OPERATOR, 'AND', 'OR', 'NOT'):
            raise ValueError(
                f"WHERE condition must be a boolean expression, got {condition.type}")

        return condition

    def _parse_where_clause(self) -> QueryTree:
        """Parse WHERE clause for UPDATE/DELETE"""
        self._expect_keyword(QueryTypes.WHERE)
        self.expr_parser.position = self.position
        self.expr_parser.current_token = self.current_token
        condition = self.expr_parser.parse_expression()
        self.position = self.expr_parser.position
        self.current_token = self.expr_parser.current_token

        if condition.type not in (QueryTypes.OPERATOR, 'AND', 'OR', 'NOT'):
            raise ValueError(
                f"WHERE condition must be a boolean expression, got {condition.type}")

        return QueryTree(type=QueryTypes.WHERE, val='', childs=[condition])

    def _parse_order_by_clause(self) -> QueryTree:
        self._expect_keyword(QueryTypes.ORDER)
        self._expect_keyword(QueryTypes.BY)
        start_pos = self.position

        columns = []
        directions = []
        while True:
            # parse column token (optionally qualified e.g., alias.column)
            if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(
                    f"Expected column name in ORDER BY, got '{bad}'")

            if self.current_token.value.upper() in ('ASC', 'DESC'):
                raise ValueError(
                    f"Expected column name in ORDER BY, got direction keyword '{self.current_token.value}'")

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
            if self._match_keyword(QueryTypes.ASC):
                self._advance()
            elif self._match_keyword(QueryTypes.DESC):
                direction = 'DESC'
                self._advance()
            columns.append(QueryTree(type=QueryTypes.COLUMN, val=column_name))
            directions.append(direction)
            if self._match_punctuation(','):
                self._advance()
                continue
            else:
                break
        order_children = []
        for col, dirn in zip(columns, directions):
            order_children.append(
                QueryTree(type=QueryTypes.ORDER_ITEM, val=dirn, childs=[col]))
        return QueryTree(type=QueryTypes.ORDER_BY, val=QueryTypes.ORDER_BY, childs=order_children)

    def _parse_limit_clause(self) -> QueryTree:
        self._expect_keyword(QueryTypes.LIMIT)
        if not self.current_token or self.current_token.type != 'NUMBER':
            bad = self.current_token.value if self.current_token else 'EOF'
            raise ValueError(
                f"Expected number in LIMIT, got '{bad}'")
        limit_val = self.current_token.value
        self._advance()

        return QueryTree(type=QueryTypes.LIMIT, val=limit_val)

    def parse_update(self) -> QueryTree:
        self._expect_keyword(QueryTypes.UPDATE)
        if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            bad = self.current_token.value if self.current_token else 'EOF'
            raise ValueError(
                f"Expected table name, got '{bad}'")
        table_name = self.current_token.value
        self._advance()

        table_node = QueryTree(type=QueryTypes.TABLE, val=table_name)

        # parse SET clause
        self._expect_keyword(QueryTypes.SET)
        set_node = self._parse_set_clause()

        # parse WHERE clause
        where_node = None
        if self._match_keyword(QueryTypes.WHERE):
            where_node = self._parse_where_clause()

        childs = [table_node, set_node]
        if where_node:
            childs.append(where_node)

        return QueryTree(type=QueryTypes.UPDATE, val=QueryTypes.UPDATE, childs=childs)

    def _parse_set_clause(self) -> QueryTree:
        assignments = []

        while True:
            # parse column = expression
            if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(
                    f"Expected column name in SET, got '{bad}'")
            column = self.current_token.value
            self._advance()

            # expect = operator
            if not self._match_operator(QueryOperators.EQ):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(
                    f"Expected '=' in SET clause, got '{bad}'")
            self._advance()

            self.expr_parser.position = self.position
            self.expr_parser.current_token = self.current_token
            value_expr = self.expr_parser.parse_expression()
            self.position = self.expr_parser.position
            self.current_token = self.expr_parser.current_token

            col_node = QueryTree(type=QueryTypes.COLUMN, val=column)
            assignment = QueryTree(type=QueryTypes.ASSIGNMENT, val=QueryOperators.EQ, childs=[
                                   col_node, value_expr])
            assignments.append(assignment)

            # cek koma (assignment selanjutnya)
            if self._match_punctuation(','):
                self._advance()
            else:
                break

        return QueryTree(type=QueryTypes.SET, val='', childs=assignments)

    def parse_delete(self) -> QueryTree:
        """Parse DELETE statement"""
        self._expect_keyword(QueryTypes.DELETE)
        self._expect_keyword(QueryTypes.FROM)
        if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            bad = self.current_token.value if self.current_token else 'EOF'
            raise ValueError(
                f"Expected table name, got '{bad}'")
        table_name = self.current_token.value
        self._advance()

        table_node = QueryTree(type=QueryTypes.TABLE, val=table_name)

        # parse WHERE clause
        where_node = None
        if self._match_keyword(QueryTypes.WHERE):
            where_node = self._parse_where_clause()

        childs = [table_node]
        if where_node:
            childs.append(where_node)

        return QueryTree(type=QueryTypes.DELETE, val=QueryTypes.DELETE, childs=childs)

    def parse_insert(self) -> QueryTree:
        """Parse INSERT statement"""
        self._expect_keyword(QueryTypes.INSERT)
        self._expect_keyword(QueryTypes.INTO)
        if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
            bad = self.current_token.value if self.current_token else 'EOF'
            raise ValueError(
                f"Expected table name, got '{bad}'")
        table_name = self.current_token.value
        self._advance()

        table_node = QueryTree(type=QueryTypes.TABLE, val=table_name)

        # parse column list (optional)
        columns_node = None
        if self._match_punctuation('('):
            columns_node = self._parse_column_list()

        # parse VALUES
        self._expect_keyword(QueryTypes.VALUES)
        values_node = self._parse_values_clause()

        childs = [table_node]
        if columns_node:
            childs.append(columns_node)
        childs.append(values_node)

        return QueryTree(type=QueryTypes.INSERT, val=QueryTypes.INSERT, childs=childs)

    def _parse_column_list(self) -> QueryTree:
        self._expect_punctuation('(')

        columns = []
        while True:
            if not self.current_token or self.current_token.type not in ('IDENTIFIER', 'KEYWORD'):
                bad = self.current_token.value if self.current_token else 'EOF'
                raise ValueError(
                    f"Expected column name, got '{bad}'")
            columns.append(QueryTree(type=QueryTypes.COLUMN,
                           val=self.current_token.value))
            self._advance()

            if self._match_punctuation(','):
                self._advance()
            else:
                break

        self._expect_punctuation(')')

        return QueryTree(type=QueryTypes.COLUMNS, val='', childs=columns)

    def _parse_values_clause(self) -> QueryTree:
        self._expect_punctuation('(')

        values = []
        while True:
            self.expr_parser.position = self.position
            self.expr_parser.current_token = self.current_token
            value_expr = self.expr_parser.parse_expression()
            self.position = self.expr_parser.position
            self.current_token = self.expr_parser.current_token
            values.append(value_expr)

            if self._match_punctuation(','):
                self._advance()
            else:
                break

        self._expect_punctuation(')')

        return QueryTree(type=QueryTypes.VALUES, val='', childs=values)
