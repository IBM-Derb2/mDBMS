from typing import Any, Dict, Set, Union
from dataclasses import dataclass, field
from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
# nyimpen 2 info timestamp (kapan terakhir dibaca & ditulis)
class TimestampEntry:
    R_TS: int = 0 
    W_TS: int = 0  
    
    def __repr__(self):
        return (f"TS_Entry(R_TS={self.R_TS}, W_TS={self.W_TS})")
    

class TimestampBasedStrategy(ConcurrencyStrategy):
    
    def __init__(self):
        # Key: object_id (string), Value: TimestampEntry
        self.timestamp_table: Dict[str, TimestampEntry] = {}
    
    # helper buat id
    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

  
    def log_object(self, obj: Any, transaction_id: int, action: str):
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()
    
        TS_T = transaction_id 
        
        print(f"[TimestampStrategy] TX {TS_T} me-log '{action_upper}' pada '{object_id}'...")

        # pastiin objeknya ada di tabel, klo ga ada bikin baru
        if object_id not in self.timestamp_table:
            self.timestamp_table[object_id] = TimestampEntry()
        
        # ambil 'cap' di objek
        entry = self.timestamp_table[object_id]

        if action_upper == 'WRITE':
            entry.W_TS = TS_T
            print(f"Sukses: WRITE log, W-TS di '{object_id}' di-update jadi {TS_T}")

        elif action_upper == 'READ':
            if TS_T > entry.R_TS:
                # Cap lebih baru, jadi kita update cap R_TS
                entry.R_TS = TS_T
                print(f"    -> Sukses: READ log, R-TS di '{object_id}' di-update jadi {TS_T}")
            else:
                # Cap kita lebih 'tua' dari R_TS yg ada
                print(f"Info: READ log, R-TS ({entry.R_TS}) >= TS({TS_T}). R-TS tidak berubah.")
                
        else:
            raise ValueError(f"Aksi unkown {action}. Gunakan 'read' atau 'write'.")



    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        print(f"[TimestampStrategy Mock] Validasi '{action}' pada '{obj}' untuk TS: {transaction_id}")
        return Response(allowed=True, transaction_id=transaction_id)


    def end_transaction(self, transaction_id: int):
        print(f"--- [TimestampStrategy] TX {transaction_id} selesai. (Ga ada yg perlu dirilis) ---")