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
            # Cek apakah ada lock yang konflik
            if object_id in self.lock_table:
                current_lock = self.lock_table[object_id]
                # Jika ada READ lock dengan multiple holders, atau lock milik TX lain
                if current_lock.lock_type == 'read' and current_lock.holders != {transaction_id}:
                    print(f"ERROR: Gagal me-log WRITE. Objek di-READ lock oleh {current_lock.holders}")
                    raise Exception(f"Pelanggaran Concurrency: Gagal me-log Write Lock")
                elif current_lock.lock_type == 'write' and transaction_id not in current_lock.holders:
                    print(f"ERROR: Gagal me-log WRITE. Objek di-WRITE lock oleh {current_lock.holders}")
                    raise Exception(f"Pelanggaran Concurrency: Gagal me-log Write Lock")

            # Baru boleh kasih WRITE lock
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
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()

        # Jika objek belum pernah di-lock, aksi diizinkan
        if object_id not in self.lock_table:
            print(f"[LockStrategy] Validasi '{action}' pada '{obj}' untuk TX {transaction_id}: DIIZINKAN (belum ada lock)")
            return Response(allowed=True, transaction_id=transaction_id)

        current_lock = self.lock_table[object_id]

        # Validasi untuk READ
        if action_upper == 'READ':
            # Jika ada READ lock, transaksi lain boleh ikut READ (shared lock)
            if current_lock.lock_type == 'read':
                print(f"[LockStrategy] Validasi READ pada '{obj}' untuk TX {transaction_id}: DIIZINKAN (shared read lock)")
                return Response(allowed=True, transaction_id=transaction_id)

            # Jika ada WRITE lock dan transaksi ini adalah pemiliknya, boleh READ
            elif current_lock.lock_type == 'write' and transaction_id in current_lock.holders:
                print(f"[LockStrategy] Validasi READ pada '{obj}' untuk TX {transaction_id}: DIIZINKAN (pemilik write lock)")
                return Response(allowed=True, transaction_id=transaction_id)

            # Jika ada WRITE lock milik transaksi lain, tidak boleh READ
            else:
                print(f"[LockStrategy] Validasi READ pada '{obj}' untuk TX {transaction_id}: DITOLAK (write lock oleh {current_lock.holders})")
                return Response(allowed=False, transaction_id=transaction_id)

        # Validasi untuk WRITE
        elif action_upper == 'WRITE':
            # Jika transaksi ini sudah punya WRITE lock, boleh WRITE lagi
            if current_lock.lock_type == 'write' and transaction_id in current_lock.holders:
                print(f"[LockStrategy] Validasi WRITE pada '{obj}' untuk TX {transaction_id}: DIIZINKAN (sudah pemilik write lock)")
                return Response(allowed=True, transaction_id=transaction_id)

            # Jika ada READ lock dan hanya transaksi ini yang punya (lock upgrade)
            elif current_lock.lock_type == 'read' and current_lock.holders == {transaction_id}:
                print(f"[LockStrategy] Validasi WRITE pada '{obj}' untuk TX {transaction_id}: DIIZINKAN (lock upgrade dari read ke write)")
                return Response(allowed=True, transaction_id=transaction_id)

            # Jika ada lock (READ atau WRITE) milik transaksi lain atau multiple holders, tidak boleh WRITE
            else:
                if current_lock.lock_type == 'read':
                    print(f"[LockStrategy] Validasi WRITE pada '{obj}' untuk TX {transaction_id}: DITOLAK (read lock oleh {current_lock.holders})")
                else:
                    print(f"[LockStrategy] Validasi WRITE pada '{obj}' untuk TX {transaction_id}: DITOLAK (write lock oleh {current_lock.holders})")
                return Response(allowed=False, transaction_id=transaction_id)

        else:
            raise ValueError(f"Aksi unknown '{action}'. Gunakan 'read' atau 'write'.")


    def end_transaction(self, transaction_id: int):
        print(f"--- [LockStrategy] Rilis lock TX {transaction_id} selesai. ---")