"""
Expression Parser
Handles parsing of SQL expressions including arithmetic, comparisons, and logical operators.
"""

from ...query_types import QueryTree
from globalsy.constants.query_types import QueryTypes
from .base_parser import BaseParser


class ExpressionParser(BaseParser):
    """Handles parsing of SQL expressions"""

    def parse_expression(self) -> QueryTree:
        """Parse an expression (supports AND, OR, comparisons, arithmetic)"""
        return self._parse_or_expression()

    def _parse_or_expression(self) -> QueryTree:
        """Parse OR expression"""
        left = self._parse_and_expression()

        while self._match_keyword('OR'):
            self._advance()
            right = self._parse_and_expression()
            left = QueryTree(type=QueryTypes.OPERATOR,
                             val='OR', childs=[left, right])

        return left

    def _parse_and_expression(self) -> QueryTree:
        """Parse AND expression"""
        left = self._parse_not_expression()

        while self._match_keyword('AND'):
            self._advance()
            right = self._parse_not_expression()
            left = QueryTree(type=QueryTypes.OPERATOR,
                             val='AND', childs=[left, right])

        return left

    def _parse_not_expression(self) -> QueryTree:
        """Parse NOT expression"""
        if self._match_keyword('NOT'):
            self._advance()
            operand = self._parse_comparison_expression()
            return QueryTree(type=QueryTypes.OPERATOR, val='NOT', childs=[operand])
        else:
            return self._parse_comparison_expression()

    def _parse_comparison_expression(self) -> QueryTree:
        """Parse comparison expression"""
        left = self._parse_additive_expression()

        # Check for comparison operators
        if self._match_operator('=') or self._match_operator('<>') or \
           self._match_operator('!=') or self._match_operator('<') or \
           self._match_operator('<=') or self._match_operator('>') or \
           self._match_operator('>='):
            op = self.current_token.value
            self._advance()
            right = self._parse_additive_expression()
            return QueryTree(type=QueryTypes.OPERATOR, val=op, childs=[left, right])

        # Handle LIKE operator
        if self._match_keyword('LIKE'):
            self._advance()
            right = self._parse_additive_expression()
            return QueryTree(type=QueryTypes.OPERATOR, val='LIKE', childs=[left, right])

        # Handle IN operator
        if self._match_keyword('IN'):
            self._advance()
            if not self._match_punctuation('('):
                raise ValueError("Expected '(' after IN")
            self._advance()

            # Parse value list
            values = []
            while True:
                value = self._parse_additive_expression()
                values.append(value)

                if self._match_punctuation(','):
                    self._advance()
                else:
                    break

            if not self._match_punctuation(')'):
                raise ValueError("Expected ')' after IN list")
            self._advance()

            return QueryTree(type=QueryTypes.OPERATOR, val='IN', childs=[left] + values)

        # Handle BETWEEN operator
        if self._match_keyword('BETWEEN'):
            self._advance()
            lower = self._parse_additive_expression()
            if not self._match_keyword('AND'):
                raise ValueError("Expected 'AND' in BETWEEN clause")
            self._advance()
            upper = self._parse_additive_expression()
            return QueryTree(type=QueryTypes.OPERATOR, val='BETWEEN', childs=[left, lower, upper])

        return left

    def _parse_additive_expression(self) -> QueryTree:
        """Parse addition/subtraction"""
        left = self._parse_multiplicative_expression()

        while self._match_operator('+') or self._match_operator('-'):
            op = self.current_token.value
            self._advance()
            right = self._parse_multiplicative_expression()
            left = QueryTree(type=QueryTypes.OPERATOR,
                             val=op, childs=[left, right])

        return left

    def _parse_multiplicative_expression(self) -> QueryTree:
        """Parse multiplication/division"""
        left = self._parse_primary_expression()

        while self._match_operator('*') or self._match_operator('/') or self._match_operator('%'):
            op = self.current_token.value
            self._advance()
            right = self._parse_primary_expression()
            left = QueryTree(type=QueryTypes.OPERATOR,
                             val=op, childs=[left, right])

        return left

    def _parse_primary_expression(self) -> QueryTree:
        """Parse primary expression (identifier, number, string, parentheses, unary minus)"""
        # Unary minus (negative numbers)
        if self._match_operator('-'):
            self._advance()
            expr = self._parse_primary_expression()
            return QueryTree(type=QueryTypes.OPERATOR, val='-', childs=[expr])

        # Parentheses
        if self._match_punctuation('('):
            self._advance()
            expr = self.parse_expression()
            self._expect_punctuation(')')
            return expr

        # String literal
        if self.current_token.type == 'STRING':
            val = self.current_token.value
            self._advance()
            return QueryTree(type=QueryTypes.LITERAL, val=f"'{val}'")

        # Number literal
        if self.current_token.type == 'NUMBER':
            val = self.current_token.value
            self._advance()
            return QueryTree(type=QueryTypes.LITERAL, val=val)

        # Identifier (column reference, possibly with table prefix)
        if self.current_token.type == 'IDENTIFIER' or self.current_token.value == '*':
            identifier = self.current_token.value
            self._advance()

            # Check for table.column syntax
            if self._match_punctuation('.'):
                self._advance()
                if self.current_token.type not in ('IDENTIFIER', 'KEYWORD') and self.current_token.value != '*':
                    raise ValueError(
                        f"Expected column name after '.', got '{self.current_token.value}'")
                column = self.current_token.value
                self._advance()
                return QueryTree(type=QueryTypes.COLUMN, val=f"{identifier}.{column}")

            return QueryTree(type=QueryTypes.COLUMN, val=identifier)

        raise ValueError(
            f"Unexpected token in expression: {self.current_token.value}")
