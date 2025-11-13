from dataclasses import dataclass
from typing import Any, Dict

# Kapasitas Buffer
BUFFER_CAPACITY = 4

@dataclass
class BufferedRow:
    # mewakili satu tuple data (block) yang disimpan pada buffer
    table_name: str
    primary_key_value: Dict[str, Any] # ID unik untuk identifikasi
    data: dict
    is_dirty: bool = False # True jika dimodifikasi dan belum ditulis ke disk
    is_pinned: bool = False # Untuk mencegah penggantian

    def __hash__(self):
        # Sebagai kunci unik dalam struktur data buffer
        return hash((self.table_name, tuple(sorted(self.primary_key_value.items()))))
    
    def __eq__(self, other):
        # Membandingkan persamaan
        if isinstance(other, BufferedRow):
            return self.__hash__() == other.__hash__()
        return False