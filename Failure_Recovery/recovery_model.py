from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

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
