from typing import Any, Dict, Set, Union
from dataclasses import dataclass, field

from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
# nyimpen 2 info locktype (read ato write dan holders nya)
class LockEntry:
    lock_type: Union['read', 'write']
    holders: Set[int] = field(default_factory=set)

    def __init__(self, lock_type: Union['read', 'write'], transaction_id: int):
        self.lock_type = lock_type
        self.holders = {transaction_id}
        
    def __repr__(self):
        return (f"Lock(type={self.lock_type}, holders={self.holders})")
    

class LockBasedStrategy(ConcurrencyStrategy):
    
    def __init__(self):
        self.lock_table: Dict[str, LockEntry] = {}
    
    #helper buat id
    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    #ada param baru action (write / read)
    def log_object(self, obj: Any, transaction_id: int, action: str):
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()
        
        if action_upper == 'WRITE':
            self.lock_table[object_id] = LockEntry('write', transaction_id)
            print(f"Sukses: WRITE lock {self.lock_table[object_id]}")

        elif action_upper == 'READ':
            # objek blm di lock samsek
            if object_id not in self.lock_table:
                self.lock_table[object_id] = LockEntry('read', transaction_id)
                print(f"Sukses: READ lock (baru) {self.lock_table[object_id]}")
            #udh ada yang lock
            else:
                current_lock = self.lock_table[object_id]
                # apakah ada Tx lain yang read, jika ya tinggal tambah holders
                if current_lock.lock_type == 'read':
                    current_lock.holders.add(transaction_id)
                    print(f"Sukses: READ lock (shared) {self.lock_table[object_id]}")

                # klo ada lock write dan dia sendiri yg punya locknya, do nothing
                elif current_lock.lock_type == 'write' and transaction_id in current_lock.holders:
                    print(f"Info: TX {transaction_id} sudah punya WRITE lock, READ diizinkan.")
                
                # ada lock write dan bukan dia sendiri yg punya locknya, ga bisa                
                else:
                    print(f"ERROR: Gagal me-log READ. Objek di-WRITE lock oleh {current_lock.holders}")
                    raise Exception(f"Pelanggaran Concurrency: Gagal me-log Read Lock")
        else:
            raise ValueError(f"Aksi unkown {action}. Gunakan 'read' atau 'write'.")


    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        print(f"[LockStrategy Mock] Validasi '{action}' pada '{obj}' untuk TX: {transaction_id}")


    def end_transaction(self, transaction_id: int):
        print(f"--- [LockStrategy] Rilis lock TX {transaction_id} selesai. ---")