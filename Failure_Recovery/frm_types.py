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
    """Represents a single data block in buffer"""
    table_name: str
    primary_key_value: Dict[str, Any]
    data: dict
    is_dirty: bool = False  # Modified but not yet written to disk
    is_pinned: bool = False  # Prevent replacement
    is_deleted: bool = False  # Marked for deletion

    def __hash__(self):
        return hash((self.table_name, tuple(sorted(self.primary_key_value.items()))))
    
    def __eq__(self, other):
        if isinstance(other, BufferedRow):
            return self.__hash__() == other.__hash__()
        return False

@dataclass
class RecoverCriteria:
    """Recovery filter criteria by timestamp or transaction_id"""
    timestamp: Optional[datetime] = None
    transaction_id: Optional[int] = None

@dataclass
class LogEntry:
    """Parsed log entry from WAL file"""
    timestamp: datetime
    transaction_id: int
    action: str
    table_name: Optional[str] = None
    pk_value: Optional[Dict[str, Any]] = None
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None
    raw_log: Dict[str, Any] = None