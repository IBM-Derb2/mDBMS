from typing import Any, Dict, Set, Union
from dataclasses import dataclass, field
from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
# nyimpen 2 set: apa yg dibaca & apa yg ditulis
class TransactionSetsEntry:
    read_set: Set[str] = field(default_factory=set)
    write_set: Set[str] = field(default_factory=set)
    
    def __repr__(self):
        return (f"Sets(Read={self.read_set}, Write={self.write_set})")
    

class ValidationBasedStrategy(ConcurrencyStrategy):
    
    def __init__(self):
        self.transaction_sets: Dict[int, TransactionSetsEntry] = {}
    
    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    def log_object(self, obj: Any, transaction_id: int, action: str):
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()
        
        print(f"[ValidationStrategy] TX {transaction_id} me-log '{action_upper}' pada '{object_id}'...")

        if transaction_id not in self.transaction_sets:
            self.transaction_sets[transaction_id] = TransactionSetsEntry()
        
        entry = self.transaction_sets[transaction_id]

        if action_upper == 'WRITE':
            entry.write_set.add(object_id)
            print(f"Sukses: WRITE log, '{object_id}' ditambah ke write_set TX {transaction_id}")

        elif action_upper == 'READ':
            # Cuma nyatet ke 'read_set' pribadinya dia
            entry.read_set.add(object_id)
            print(f"Sukses: READ log, '{object_id}' ditambah ke read_set TX {transaction_id}")
                
        else:
            raise ValueError(f"Aksi unkown {action}. Gunakan 'read' atau 'write'.")



    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()

        # Validation-based strategy menggunakan optimistic concurrency control
        # Validasi dilakukan saat commit, bukan saat akses
        # Di fase READ/WRITE, semua aksi diizinkan terlebih dahulu

        if action_upper == 'READ':
            print(f"[ValidationStrategy] Validasi READ pada '{object_id}' untuk TX {transaction_id}: DIIZINKAN (optimistic, akan divalidasi saat commit)")
            return Response(allowed=True, transaction_id=transaction_id)

        elif action_upper == 'WRITE':
            # Cek apakah ada transaksi lain yang sedang menulis objek yang sama
            # (dalam implementasi sederhana, kita izinkan dulu)
            conflict = False
            conflicting_tx = []

            for tx_id, entry in self.transaction_sets.items():
                if tx_id != transaction_id:
                    # Cek apakah ada transaksi lain yang menulis objek yang sama
                    if object_id in entry.write_set:
                        conflict = True
                        conflicting_tx.append(tx_id)

            if conflict:
                print(f"[ValidationStrategy] Validasi WRITE pada '{object_id}' untuk TX {transaction_id}: WARNING - konflik dengan TX {conflicting_tx} (optimistic, tetap diizinkan sementara)")
                # Dalam optimistic CC, tetap izinkan dan validasi nanti saat commit
                return Response(allowed=True, transaction_id=transaction_id)
            else:
                print(f"[ValidationStrategy] Validasi WRITE pada '{object_id}' untuk TX {transaction_id}: DIIZINKAN (optimistic, akan divalidasi saat commit)")
                return Response(allowed=True, transaction_id=transaction_id)

        else:
            raise ValueError(f"Aksi unknown '{action}'. Gunakan 'read' atau 'write'.")


    def end_transaction(self, transaction_id: int):
        print(f"[ValidationStrategy] TX {transaction_id} selesai")
        if transaction_id in self.transaction_sets:
            del self.transaction_sets[transaction_id]