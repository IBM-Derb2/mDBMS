"""
Base SQL Parser
Contains core parsing utilities and base parser class.
"""

from typing import List, Optional
import logging
from ...query_types import QueryTree
from ..helpers.tokenizer import SQLToken


class BaseParser:
    """Base parser class with common parsing utilities"""

    def __init__(self, tokens: List[SQLToken], logger: Optional[logging.Logger] = None):
        self.tokens = tokens
        self.position = 0
        self.current_token = tokens[0] if tokens else None
        self.logger = logger

    def _advance(self):
        """Advance to next token"""
        self.position += 1
        if self.position < len(self.tokens):
            self.current_token = self.tokens[self.position]
        else:
            self.current_token = None

    def _match_keyword(self, keyword: str) -> bool:
        """Check if current token matches keyword"""
        return (self.current_token and
                self.current_token.type == 'KEYWORD' and
                self.current_token.value.upper() == keyword.upper())

    def _match_operator(self, operator: str) -> bool:
        """Check if current token matches operator"""
        return (self.current_token and
                self.current_token.type == 'OPERATOR' and
                self.current_token.value == operator)

    def _match_punctuation(self, punct: str) -> bool:
        """Check if current token matches punctuation"""
        return (self.current_token and
                self.current_token.type == 'PUNCTUATION' and
                self.current_token.value == punct)

    def _expect_keyword(self, keyword: str):
        """Expect and consume keyword, raise error if not found"""
        if not self._match_keyword(keyword):
            raise ValueError(
                f"Expected keyword '{keyword}', got '{self.current_token.value if self.current_token else 'EOF'}'")
        self._advance()

    def _expect_punctuation(self, punct: str):
        """Expect and consume punctuation, raise error if not found"""
        if not self._match_punctuation(punct):
            raise ValueError(
                f"Expected '{punct}', got '{self.current_token.value if self.current_token else 'EOF'}'")
        self._advance()
