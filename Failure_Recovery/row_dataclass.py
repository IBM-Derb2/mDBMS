from dataclasses import dataclass
from typing import Any

# Kapasitas Buffer
BUFFER_CAPACITY = 4

@dataclass
class BufferedRow:
    # mewakili satu tuple data (block) yang disimpan pada buffer
    table_name: str
    primary_key_value: Any # ID unik untuk identifikasi
    data: dict
    is_dirty: bool = False # True jika dimodifikasi dan belum ditulis ke disk
    is_pinned: bool = False # Untuk mencegah penggantian

    def __hash__(self):
        # Sebagai kunci unik dalam struktur data buffer
        return hash((self.table_name, self.primary_key_value))
    
    def __eq__(self, other):
        # Membandingkan persamaan
        if isinstance(other, BufferedRow):
            return (self.table_name, self.primary_key_value) == (other.table_name, other.primary_key_value)
        return False