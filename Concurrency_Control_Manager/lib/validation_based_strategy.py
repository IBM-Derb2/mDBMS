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
        print(f"[ValidationStrategy Mock] Validasi '{action}' pada '{obj}' untuk TX: {transaction_id}")
        return Response(allowed=True, transaction_id=transaction_id)


    def end_transaction(self, transaction_id: int):
        print(f"[ValidationStrategy] TX {transaction_id} selesai")
        if transaction_id in self.transaction_sets:
            del self.transaction_sets[transaction_id]