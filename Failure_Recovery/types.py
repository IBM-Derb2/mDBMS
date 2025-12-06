from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

BUFFER_CAPACITY = 4

class WalType(Enum):
    EXECUTION = "execution"
    CHECKPOINT = "checkpoint"

class WalAction(Enum):
    START = "start"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    COMMIT = "commit"
    ABORT = "abort"

@dataclass
class BufferedRow:
    # mewakili satu tuple data (block) yang disimpan pada buffer
    table_name: str
    primary_key_value: Dict[str, Any] # ID unik untuk identifikasi
    data: dict
    is_dirty: bool = False # True jika dimodifikasi dan belum ditulis ke disk
    is_pinned: bool = False # Untuk mencegah penggantian
    is_deleted: bool = False # True if marked for deletion

    def __hash__(self):
        # Sebagai kunci unik dalam struktur data buffer
        return hash((self.table_name, tuple(sorted(self.primary_key_value.items()))))
    
    def __eq__(self, other):
        # Membandingkan persamaan
        if isinstance(other, BufferedRow):
            return self.__hash__() == other.__hash__()
        return False
    
@dataclass
class RecoverCriteria:
    # object, berisi checkpoint yang digunakan untuk recovery
    # dapat berupa timestamp atau transaction_id, atau keduanya, atau tidak ada sama sekali
    timestamp: Optional[datetime] = None
    transaction_id: Optional[int] = None

@dataclass
class LogEntry:
    # kelas log entry, hasil pembacaan dan parsing dari file log yang sudah ada
    timestamp: datetime
    transaction_id: int
    action: str
    
    # Opsional, hanya jika action adalah WRITE
    table_name: Optional[str] = None
    pk_value: Optional[Dict[str, Any]] = None
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None

    raw_log: Dict[str, Any] = None # menyimpan log dict asli sebagai backup
