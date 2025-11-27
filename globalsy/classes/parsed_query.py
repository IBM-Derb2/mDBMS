from __future__ import annotations
from .query_tree import QueryTree


class ParsedQuery:
    def __init__(self, query_tree: QueryTree, query: str):
        self.query_tree = query_tree
        self.query = query

    # untuk testing
    def __repr__(self) -> str:
        return f"ParsedQuery(query='{self.query}')"

    def __str__(self) -> str:
        header = f"Query: '{self.query}'"
        divider = "-" * (len(header) if len(header) > 18 else 18)

        tree_str = str(self.query_tree)

        return f"{header}\n{divider}\n{tree_str}"
