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
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()
        TS_T = transaction_id

        # Validasi untuk READ
        if action_upper == 'READ':
            # Jika objek belum punya versi sama sekali, izinkan (akan baca versi kosong/default)
            if object_id not in self.version_store or len(self.version_store[object_id]) == 0:
                print(f"[MVCCStrategy] Validasi READ pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (belum ada versi)")
                return Response(allowed=True, transaction_id=transaction_id)

            # Cari versi yang tepat: versi dengan created_ts <= TS_T dan expired_ts > TS_T
            versions_list = self.version_store[object_id]
            found_version = None

            for version in reversed(versions_list):
                if version.created_ts <= TS_T < version.expired_ts:
                    found_version = version
                    break

            if found_version:
                print(f"[MVCCStrategy] Validasi READ pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (versi ditemukan: created={found_version.created_ts}, expired={found_version.expired_ts})")
                return Response(allowed=True, transaction_id=transaction_id)
            else:
                # Cari versi terakhir sebelum TS_T (versi dengan created_ts terbesar yang < TS_T dan sudah expired)
                fallback_version = None
                for version in reversed(versions_list):
                    if version.created_ts < TS_T:
                        fallback_version = version
                        break

                if fallback_version:
                    print(f"[MVCCStrategy] Validasi READ pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (baca versi lama: created={fallback_version.created_ts}, expired={fallback_version.expired_ts})")
                    return Response(allowed=True, transaction_id=transaction_id)
                else:
                    # Tidak ada versi yang bisa dibaca (semua versi lebih baru dari TS_T)
                    print(f"[MVCCStrategy] Validasi READ pada '{object_id}' untuk TS {TS_T}: DITOLAK (semua versi lebih baru dari TS ini)")
                    return Response(allowed=False, transaction_id=transaction_id)

        # Validasi untuk WRITE
        elif action_upper == 'WRITE':
            # Di MVCC, WRITE selalu membuat versi baru, jadi biasanya selalu diizinkan
            # Namun, perlu cek apakah ada konflik dengan versi yang sedang dibaca transaksi lain

            # Implementasi sederhana: izinkan WRITE, akan membuat versi baru
            print(f"[MVCCStrategy] Validasi WRITE pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (akan membuat versi baru)")
            return Response(allowed=True, transaction_id=transaction_id)

        else:
            raise ValueError(f"Aksi unknown '{action}'. Gunakan 'read' atau 'write'.")


    def end_transaction(self, transaction_id: int):
        print(f"[MVCCStrategy] TX {transaction_id} selesai.")