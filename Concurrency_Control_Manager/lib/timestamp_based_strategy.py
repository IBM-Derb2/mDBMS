from typing import Any, Dict, Set, Union
from dataclasses import dataclass, field
from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
# nyimpen 2 info timestamp (kapan terakhir dibaca & ditulis)
class TimestampEntry:
    R_TS: int = 0
    W_TS: int = 0

    def __repr__(self):
        return f"TS_Entry(R_TS={self.R_TS}, W_TS={self.W_TS})"


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

        print(
            f"[TimestampStrategy] TX {TS_T} me-log '{action_upper}' pada '{object_id}'..."
        )

        # pastiin objeknya ada di tabel, klo ga ada bikin baru
        if object_id not in self.timestamp_table:
            self.timestamp_table[object_id] = TimestampEntry()

        # ambil 'cap' di objek
        entry = self.timestamp_table[object_id]

        if action_upper == "WRITE":
            entry.W_TS = TS_T
            print(f"Sukses: WRITE log, W-TS di '{object_id}' di-update jadi {TS_T}")

        elif action_upper == "READ":
            # R-TS harus di-update ke maksimum dari R-TS saat ini dan TS(T)
            old_r_ts = entry.R_TS
            entry.R_TS = max(entry.R_TS, TS_T)
            if entry.R_TS > old_r_ts:
                print(
                    f"    -> Sukses: READ log, R-TS di '{object_id}' di-update dari {old_r_ts} jadi {entry.R_TS}"
                )
            else:
                print(
                    f"    -> Info: READ log, R-TS ({entry.R_TS}) sudah >= TS({TS_T}). R-TS tidak berubah."
                )

        else:
            raise ValueError(f"Aksi unkown {action}. Gunakan 'read' atau 'write'.")

    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()
        TS_T = transaction_id

        # Jika objek belum pernah diakses, aksi diizinkan
        if object_id not in self.timestamp_table:
            print(
                f"[TimestampStrategy] Validasi '{action}' pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (objek baru)"
            )
            return Response(allowed=True, transaction_id=transaction_id)

        entry = self.timestamp_table[object_id]

        # Validasi untuk READ
        if action_upper == "READ":
            # Aturan: TS(T) >= W-TS(X)
            # Transaksi hanya boleh membaca jika timestamp-nya >= timestamp terakhir yang menulis
            if TS_T >= entry.W_TS:
                print(
                    f"[TimestampStrategy] Validasi READ pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (TS >= W-TS={entry.W_TS})"
                )
                return Response(allowed=True, transaction_id=transaction_id)
            else:
                # TS(T) < W-TS(X) → transaksi terlambat, harus di-abort
                print(
                    f"[TimestampStrategy] Validasi READ pada '{object_id}' untuk TS {TS_T}: DITOLAK (TS < W-TS={entry.W_TS})"
                )
                return Response(allowed=False, transaction_id=transaction_id)

        # Validasi untuk WRITE
        elif action_upper == "WRITE":
            # Aturan: TS(T) >= R-TS(X) dan TS(T) >= W-TS(X)
            # Transaksi hanya boleh menulis jika timestamp-nya >= timestamp terakhir yang membaca DAN menulis
            if TS_T >= entry.R_TS and TS_T >= entry.W_TS:
                print(
                    f"[TimestampStrategy] Validasi WRITE pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (TS >= R-TS={entry.R_TS} dan W-TS={entry.W_TS})"
                )
                return Response(allowed=True, transaction_id=transaction_id)
            else:
                # Transaksi terlambat, harus di-abort
                if TS_T < entry.R_TS:
                    print(
                        f"[TimestampStrategy] Validasi WRITE pada '{object_id}' untuk TS {TS_T}: DITOLAK (TS < R-TS={entry.R_TS})"
                    )
                else:
                    print(
                        f"[TimestampStrategy] Validasi WRITE pada '{object_id}' untuk TS {TS_T}: DITOLAK (TS < W-TS={entry.W_TS})"
                    )
                return Response(allowed=False, transaction_id=transaction_id)

        else:
            raise ValueError(f"Aksi unknown '{action}'. Gunakan 'read' atau 'write'.")

    def end_transaction(self, transaction_id: int):
        print(
            f"--- [TimestampStrategy] TX {transaction_id} selesai. (Ga ada yg perlu dirilis) ---"
        )
