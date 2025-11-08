from typing import Union
from index_type_enum import IndexTypeEnum
from b_plus_tree_index import BPlusTreeIndex
from hash_index import HashIndex

class StorageEngine:
    def __init__(self):
        pass

    def set_index(self, table: str, column: str, index_type:Union[str | IndexTypeEnum]) -> None:
        """
        table: table name to be indexed
        column: column name to be indexed
        index_type: index thats gonna be used, either (IndexTypeEnum.B_PLUS_TREE or "B+ Tree") or (IndexTypeEnum.HASH or "Hash")
        """
        if index_type.lower() not in ["b+ tree", "hash"]:
            raise ValueError("index_type should be 'b+ tree' or 'hash'") 
        if isinstance(index_type, str):
            index_type = index_type.lower()

        # TODO: Load data 

        if index_type in [IndexTypeEnum.B_PLUS_TREE, "b+ tree"]:
            indexer = BPlusTreeIndex()
            # TODO: do indexing, depends on data format
            pass 
        elif index_type in [IndexTypeEnum.HASH, "hash"]:
            indexer = HashIndex()
            # TODO: do indexing, depends on data format
            pass

        return None
