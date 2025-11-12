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
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None

    raw_log: Dict[str, Any] = None # menyimpan log dict asli sebagai backup

class MockQueryProcessor():
    # mock query processor untuk simulasi logika undo
    def apply_undo(self, table_name: str, old_values: Optional[Dict[str, Any]], new_values: Optional[Dict[str, Any]] = None) -> None:
        def eq_clause(d: Dict[str, Any]) -> str:
            # buat klausa equality untuk "col='value' AND ..."
            return " AND ".join([f"{k}='{v}'" for k, v in d.items()]) if d else "1=1"

        # Bangun klausa WHERE berdasarkan nilai 'new_values' jika ada, fallbacknya menggunakan 'old_values'. 
        match = new_values if new_values else old_values
        where_clause = eq_clause(match) if match else "1=1"

        if old_values is None:
            # undo INSERT: -> DELETE
            action = f"DELETE FROM {table_name} WHERE {where_clause}"
        else:
            # undo UPDATE/DELETE: -> set ke old_values hanya jika baris saat ini cocok dengan new_values
            set_clause = ", ".join([f"{k}='{v}'" for k, v in old_values.items()])
            action = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"

        print(f"[MockQueryProcessor] akan mengeksekusi query: {action}")