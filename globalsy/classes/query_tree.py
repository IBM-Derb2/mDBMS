from __future__ import annotations
from typing import Optional, List
from ..constants.query_types import QueryTypes


class QueryTree:
    def __init__(self,
                 type: QueryTypes,
                 val: str,
                 childs: Optional[List['QueryTree']] = None,
                 parent: Optional['QueryTree'] = None):

        # avoid mutable default for childs
        if childs is None:
            childs = []

        if type is None:
            raise ValueError("type tidak boleh None")

        if type not in vars(QueryTypes).values():
            raise ValueError(f"type '{type}' tidak valid dalam QueryTypes")

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
            tree_string += child._build_tree_string(
                prefix="", is_last=is_last_child)

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
            line += child._build_tree_string(child_prefix,
                                             is_last=is_last_child)

        return line
