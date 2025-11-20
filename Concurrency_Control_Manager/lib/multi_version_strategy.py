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
        return f"\n    Ver(Data={self.data}, TS_Create={self.created_ts}, TS_Expire={self.expired_ts})"


class MultiVersionStrategy(ConcurrencyStrategy):

    def __init__(self):
        self.version_store: Dict[str, List[Version]] = {}
        self.tx_manager_ref = None  # Reference to transaction manager
        self.verbose = True

    def set_transaction_manager(self, tx_manager):
        """Set reference to transaction manager for GC."""
        self.tx_manager_ref = tx_manager

    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    def log_object(self, obj: Any, transaction_id: int, action: str):
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()
        TS_T = transaction_id

        print(f"[MVCCStrategy] TX {TS_T} me-log '{action_upper}' pada '{object_id}'...")

        if action_upper == "WRITE":
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
                    print(
                        f"    -> Info: Versi lama (TS_Create={v.created_ts}) 'dimatikan' di TS {TS_T}"
                    )
                    break

            # Tambah versi baru
            versions_list.append(new_version)
            print(
                f"    -> Sukses: WRITE log, VERSI BARU dibuat untuk '{object_id}' di TS {TS_T}"
            )

        elif action_upper == "READ":
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
        if action_upper == "READ":
            # Jika objek belum punya versi sama sekali, izinkan (akan baca versi kosong/default)
            if (
                object_id not in self.version_store
                or len(self.version_store[object_id]) == 0
            ):
                print(
                    f"[MVCCStrategy] Validasi READ pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (belum ada versi)"
                )
                return Response(allowed=True, transaction_id=transaction_id)

            # Cari versi yang tepat: versi dengan created_ts <= TS_T dan expired_ts > TS_T
            # Untuk versi yang masih live (expired_ts = 999999), kondisi expired_ts > TS_T pasti terpenuhi
            versions_list = self.version_store[object_id]
            found_version = None

            for version in reversed(versions_list):
                # Versi valid jika: created sebelum/saat TS(T) DAN belum expired saat TS(T)
                if version.created_ts <= TS_T and version.expired_ts > TS_T:
                    found_version = version
                    break

            if found_version:
                print(
                    f"[MVCCStrategy] Validasi READ pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (versi ditemukan: created={found_version.created_ts}, expired={found_version.expired_ts})"
                )
                return Response(allowed=True, transaction_id=transaction_id)
            else:
                # Cari versi terakhir sebelum TS_T (versi dengan created_ts terbesar yang < TS_T dan sudah expired)
                fallback_version = None
                for version in reversed(versions_list):
                    if version.created_ts < TS_T:
                        fallback_version = version
                        break

                if fallback_version:
                    print(
                        f"[MVCCStrategy] Validasi READ pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (baca versi lama: created={fallback_version.created_ts}, expired={fallback_version.expired_ts})"
                    )
                    return Response(allowed=True, transaction_id=transaction_id)
                else:
                    # Tidak ada versi yang bisa dibaca (semua versi lebih baru dari TS_T)
                    print(
                        f"[MVCCStrategy] Validasi READ pada '{object_id}' untuk TS {TS_T}: DITOLAK (semua versi lebih baru dari TS ini)"
                    )
                    return Response(allowed=False, transaction_id=transaction_id)

        # Validasi untuk WRITE
        elif action_upper == "WRITE":
            # Di MVCC dengan first-committer-wins:
            # Cek apakah ada versi yang dibuat oleh transaksi dengan timestamp lebih besar dari kita
            # Jika ada, berarti transaksi lain sudah commit duluan -> kita harus abort

            if object_id in self.version_store:
                versions_list = self.version_store[object_id]
                # Cek apakah ada versi dengan created_ts yang lebih besar dari TS_T tapi lebih kecil dari sekarang
                for version in versions_list:
                    # Jika ada versi yang dibuat setelah timestamp kita, ada konflik
                    if TS_T < version.created_ts:
                        print(
                            f"[MVCCStrategy] Validasi WRITE pada '{object_id}' untuk TS {TS_T}: DITOLAK (first-committer-wins: versi TS {version.created_ts} sudah ada)"
                        )
                        return Response(allowed=False, transaction_id=transaction_id)

            # Tidak ada konflik, izinkan WRITE
            print(
                f"[MVCCStrategy] Validasi WRITE pada '{object_id}' untuk TS {TS_T}: DIIZINKAN (akan membuat versi baru)"
            )
            return Response(allowed=True, transaction_id=transaction_id)

        else:
            raise ValueError(f"Aksi unknown '{action}'. Gunakan 'read' atau 'write'.")

    def end_transaction(self, transaction_id: int):
        if self.verbose:
            print(f"[MVCCStrategy] TX {transaction_id} selesai.")

        # Trigger garbage collection after transaction ends
        self.garbage_collect_versions()

    def garbage_collect_versions(self):
        """
        Remove old versions that are no longer needed.

        A version can be garbage collected if:
        1. It has expired (expired_ts != 999999)
        2. No active transaction could possibly read it
           (its expired_ts < oldest_active_transaction_ts)
        """
        if not self.tx_manager_ref:
            return

        # Get oldest active transaction timestamp
        active_txs = self.tx_manager_ref.active_transactions
        if not active_txs:
            # No active transactions, can't GC safely
            return

        oldest_active_ts = min(active_txs) if active_txs else 999999

        gc_count = 0
        total_versions_before = sum(
            len(versions) for versions in self.version_store.values()
        )

        # Clean up old versions for each object
        for obj_id in list(self.version_store.keys()):
            versions_list = self.version_store[obj_id]

            # Keep only versions that:
            # - Are still live (expired_ts == 999999), OR
            # - Could still be read by active transactions (expired_ts >= oldest_active_ts)
            cleaned_versions = [
                v
                for v in versions_list
                if v.expired_ts == 999999 or v.expired_ts >= oldest_active_ts
            ]

            gc_count += len(versions_list) - len(cleaned_versions)

            if cleaned_versions:
                self.version_store[obj_id] = cleaned_versions
            else:
                # No versions left, remove object entirely
                del self.version_store[obj_id]

        total_versions_after = sum(
            len(versions) for versions in self.version_store.values()
        )

        if self.verbose and gc_count > 0:
            print(
                f"[MVCCStrategy] Garbage collected {gc_count} old versions "
                f"({total_versions_before} -> {total_versions_after} versions)"
            )

    def print_version_store(self):
        """Print all versions for debugging."""
        print("\n" + "=" * 60)
        print("MVCC VERSION STORE")
        print("=" * 60)
        if not self.version_store:
            print("(empty)")
        else:
            for obj_id, versions in self.version_store.items():
                print(f"\nObject '{obj_id}': {len(versions)} version(s)")
                for i, version in enumerate(versions, 1):
                    status = "LIVE" if version.expired_ts == 999999 else "EXPIRED"
                    print(
                        f"  {i}. {status} - Created: TS{version.created_ts}, "
                        f"Expired: {'INF' if version.expired_ts == 999999 else f'TS{version.expired_ts}'}"
                    )
        print("=" * 60 + "\n")

    def get_statistics(self) -> Dict[str, Any]:
        """Get MVCC statistics."""
        total_objects = len(self.version_store)
        total_versions = sum(len(versions) for versions in self.version_store.values())
        live_versions = sum(
            sum(1 for v in versions if v.expired_ts == 999999)
            for versions in self.version_store.values()
        )
        expired_versions = total_versions - live_versions

        avg_versions_per_object = (
            total_versions / total_objects if total_objects > 0 else 0
        )

        return {
            "total_objects": total_objects,
            "total_versions": total_versions,
            "live_versions": live_versions,
            "expired_versions": expired_versions,
            "avg_versions_per_object": avg_versions_per_object,
        }
