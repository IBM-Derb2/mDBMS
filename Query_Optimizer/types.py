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

    # untuk testing
    def __str__(self) -> str:
        # Cetak node root (dirinya sendiri)
        tree_string = f"{self.type}: {self.val}\n"
        
        child_count = len(self.childs)
        for i, child in enumerate(self.childs):
            is_last_child = (i == child_count - 1)
            tree_string += child._build_tree_string(prefix="", is_last=is_last_child)
            
        return tree_string.strip() 

    def _build_tree_string(self, prefix: str, is_last: bool) -> str:
        branch = "+-- " if is_last else "|-- "
        
        # Buat baris untuk node ini
        line = prefix + branch + f"{self.type}: {self.val}\n"
        
        child_prefix = prefix + ("    " if is_last else "|   ")
        
        # Panggil rekursif untuk semua anak dari node ini
        child_count = len(self.childs)
        for i, child in enumerate(self.childs):
            is_last_child = (i == child_count - 1)
            line += child._build_tree_string(child_prefix, is_last=is_last_child)
            
        return line


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