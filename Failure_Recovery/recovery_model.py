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

class MockQueryProcessor():
    # mock query processor untuk simulasi logika undo
    def apply_undo(self, table_name: str, pk: Optional[Dict[str, Any]], old_values: Optional[Dict[str, Any]], new_values: Optional[Dict[str, Any]] = None) -> None:
        def eq_clause(d: Dict[str, Any]) -> str:
            # buat klausa equality untuk "col='value' AND ..."
            return " AND ".join([f"{k}='{v}'" for k, v in d.items()]) if d else "1=1"
        
        # Bangun klausa WHERE menggunakan pk_value dan match dari atribut yang diinsert/update pada new_values
        match = new_values if new_values else old_values

        # jika ada pk, hapus field pk pada match
        if isinstance(pk, dict) and isinstance(match, dict):
            match_no_pk = {k: v for k, v in match.items() if k not in pk}
        else:
            match_no_pk = match

        match_clause = eq_clause(match_no_pk) if match_no_pk else "1=1"

        # untuk kasus primary key tidak ada
        pk_clause = ""
        if pk is None:
            pk_clause = ""
        else:
            pk_clause = eq_clause(pk)

        if pk_clause and match_clause and match_clause != "1=1":
            where_clause = pk_clause + " AND " + match_clause
        elif pk_clause:
            where_clause = pk_clause
        else:
            where_clause = match_clause

        if old_values is None:
            # undo INSERT -> DELETE baris yang cocok
            action = f"DELETE FROM {table_name} WHERE {where_clause}"
        else:
            # undo UPDATE/DELETE -> kembalikan nilai lama
            set_clause = ", ".join([f"{k}='{v}'" for k, v in old_values.items()]) if old_values else ""
            action = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"

        print(f"[MockQueryProcessor] akan mengeksekusi query: {action}")