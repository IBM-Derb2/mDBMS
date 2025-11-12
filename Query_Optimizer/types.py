from __future__ import annotations
from typing import Optional, List


class QueryTree:
    def __init__(self,
                 type: str,
                 val: str,
                 childs: Optional[List['QueryTree']] = None,
                 parent: Optional['QueryTree'] = None):

        # avoid mutable default for childs
        if childs is None:
            childs = []

        self.type = type
        self.val = val
        self.childs = childs
        self.parent = parent


class ParsedQuery:
    def __init__(self, query_tree: QueryTree, query: str):
        self.query_tree = query_tree
        self.query = query
