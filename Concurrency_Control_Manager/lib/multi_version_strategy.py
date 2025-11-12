from typing import Any, Dict, Set, Union, List
from dataclasses import dataclass, field
from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
# nyimpen data + cap waktu kapan dia dibuat & kapan dia mati
class Version:
    data: Any      
    created_ts: int 
    expired_ts: int 
    
    def __repr__(self):
        return (f"\n    Ver(Data={self.data}, TS_Create={self.created_ts}, TS_Expire={self.expired_ts})")
    

class MultiVersionStrategy(ConcurrencyStrategy):
    
    def __init__(self):
        self.version_store: Dict[str, List[Version]] = {}
    
    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    def log_object(self, obj: Any, transaction_id: int, action: str):
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()
        TS_T = transaction_id 
        
        print(f"[MVCCStrategy] TX {TS_T} me-log '{action_upper}' pada '{object_id}'...")

        if action_upper == 'WRITE':
            new_version = Version(data=obj, created_ts=TS_T, expired_ts=999999)
            if object_id not in self.version_store:
                self.version_store[object_id] = []
            
            versions_list = self.version_store[object_id]

            # Matiin versi lama yg masihhidup
            found_current = False
            for v in reversed(versions_list):
                if v.expired_ts == 999999:
                    v.expired_ts = TS_T 
                    found_current = True
                    print(f"    -> Info: Versi lama (TS_Create={v.created_ts}) 'dimatikan' di TS {TS_T}")
                    break
            
            # Tambah versi baru
            versions_list.append(new_version)
            print(f"    -> Sukses: WRITE log, VERSI BARU dibuat untuk '{object_id}' di TS {TS_T}")

        elif action_upper == 'READ':
            # Di MVCC, 'log_object' ga perlu ngapa-ngapain pas READ
            # 'validate_object' yg bertugas nyariin versi
            print(f"    -> Info: READ tidak dicatat oleh log_object di MVCC.")
                
        else:
            raise ValueError(f"Aksi unkown {action}. Gunakan 'read' atau 'write'.")


    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        print(f"[MVCCStrategy Mock] Validasi '{action}' pada '{obj}' untuk TS: {transaction_id}")
        return Response(allowed=True, transaction_id=transaction_id)


    def end_transaction(self, transaction_id: int):
        print(f"[MVCCStrategy] TX {transaction_id} selesai.")