from enum import Enum
from dataclasses import dataclass
from typing import Any, Union, Optional

# ===== NEW: WAL Structure sesuai Guidebook =====
class WalType(Enum):
    """Type of WAL entry"""
    EXECUTION = "execution"
    CHECKPOINT = "checkpoint"

class WalAction(Enum):
    """Action untuk execution entries"""
    START = "start"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    COMMIT = "commit"
    ABORT = "abort"

# ===== LEGACY: Keep untuk backward compatibility =====
class ActionType(Enum):
    """Legacy enum - untuk code yang sudah ada"""
    START = 0
    WRITE = 1
    COMMIT = 2
    ABORT = 3

# ===== Data Classes =====
@dataclass
class MockExecutionResult:
    """Mock dari data yang dikirim oleh query processor"""
    transaction_id: int
    query: str
    data: Any

@dataclass
class MockChangeReport:
    """Mock dari laporan perubahan yang dikasi oleh Buffer Manager"""
    table_name: str
    pk_value: Optional[dict[str, Any]] = None
    old_data: Union[dict, None] = None  # None = INSERT
    new_data: Union[dict, None] = None  # None = DELETE