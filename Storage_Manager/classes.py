from dataclasses import dataclass, field
from typing import List, Any

@dataclass
class Rows:
    data: List[dict] = field(default_factory=list)

# 
class StorageEngine:
    
    def read_block(self, data_retrieval: Any) -> Rows:
        print(f"[Storage Mock] Reading block based on: '{data_retrieval}'")
        dummy_data = [
            {"id": 1, "name": "Alice", "salary": 1200},
            {"id": 2, "name": "Bob", "salary": 900}
        ]
        return Rows(data=dummy_data)

    def write_block(self, data_write: Any) -> int:
        print(f"[Storage Mock] Writing block based on: '{data_write}'")
        return 1

    def delete_block(self, data_deletion: Any) -> int:
        print(f"[Storage Mock] Deleting block based on: '{data_deletion}'")
        return 1 # 1 baris dummy terhapus

    def set_index(self, table: str, column: str, index_type: str):
        print(f"[Storage Mock] Setting index '{index_type}' on {table}.{column}")
        
    def get_stats(self) -> Any:
        print("[Storage Mock] Getting statistics...")
        return {"n_r": 100, "b_r": 10} # Dummy stats