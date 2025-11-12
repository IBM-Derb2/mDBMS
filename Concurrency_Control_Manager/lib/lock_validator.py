from typing import Any, Dict, Set, Union, Literal
from dataclasses import dataclass

from .strategy_interface import Response


@dataclass
class LockEntry:
    lock_type: Literal["read", "write"]
    holders: Set[int]

    def __repr__(self):
        return f"Lock(type={self.lock_type}, holders={self.holders})"


class LockValidator:
    @staticmethod
    def validate_read_operation(
        object_id: str,
        transaction_id: int,
        current_lock: LockEntry,
        verbose: bool = True,
    ) -> Response:
        # Rule 1: Shared READ lock - multiple readers allowed
        if current_lock.lock_type == "read":
            if verbose:
                print(f"  ✓ ALLOWED: Shared READ lock exists, READ diizinkan")
            return Response(allowed=True, transaction_id=transaction_id)

        # Rule 2 & 3: WRITE lock exists
        elif current_lock.lock_type == "write":
            # Transaksi sendiri yang punya WRITE lock
            if transaction_id in current_lock.holders:
                if verbose:
                    print(
                        f"  ✓ ALLOWED: TX {transaction_id} sudah punya WRITE lock, READ diizinkan"
                    )
                return Response(allowed=True, transaction_id=transaction_id)

            # Transaksi lain yang punya WRITE lock
            else:
                if verbose:
                    print(
                        f"  ✗ DENIED: Objek di-WRITE lock oleh TX {current_lock.holders}, READ ditolak"
                    )
                return Response(allowed=False, transaction_id=transaction_id)

        # Unexpected lock type
        return Response(allowed=False, transaction_id=transaction_id)

    @staticmethod
    def validate_write_operation(
        object_id: str,
        transaction_id: int,
        current_lock: LockEntry,
        verbose: bool = True,
    ) -> Response:
        # Jika transaksi sendiri yang punya lock
        if transaction_id in current_lock.holders:

            # Rule 1: Sudah punya WRITE lock
            if current_lock.lock_type == "write":
                if verbose:
                    print(f"  ✓ ALLOWED: TX {transaction_id} sudah punya WRITE lock")
                return Response(allowed=True, transaction_id=transaction_id)

            # Rule 2 & 3: Punya READ lock - cek apakah bisa upgrade
            elif current_lock.lock_type == "read":
                # Rule 2: Exclusive READ lock - bisa upgrade
                if len(current_lock.holders) == 1:
                    if verbose:
                        print(
                            f"  ✓ ALLOWED: TX {transaction_id} bisa upgrade READ lock ke WRITE"
                        )
                    return Response(allowed=True, transaction_id=transaction_id)

                # Rule 3: Shared READ lock - tidak bisa upgrade
                else:
                    if verbose:
                        print(
                            f"  ✗ DENIED: Tidak bisa upgrade, ada TX lain dalam shared READ lock"
                        )
                    return Response(allowed=False, transaction_id=transaction_id)

        # Rule 4: Transaksi lain yang punya lock
        else:
            if verbose:
                print(
                    f"  ✗ DENIED: Objek di-lock oleh TX {current_lock.holders}, WRITE ditolak"
                )
            return Response(allowed=False, transaction_id=transaction_id)

        # Default: tidak diizinkan
        return Response(allowed=False, transaction_id=transaction_id)

    @staticmethod
    def validate_operation(
        object_id: str,
        transaction_id: int,
        action: str,
        lock_table: Dict[str, LockEntry],
        verbose: bool = True,
    ) -> Response:
        action_upper = action.strip().upper()

        if verbose:
            print(
                f"[LockValidator] Validasi '{action_upper}' pada objek '{object_id}' untuk TX {transaction_id}"
            )

        # Jika objek belum di-lock sama sekali, operasi selalu diizinkan
        if object_id not in lock_table:
            if verbose:
                print(f"  ✓ ALLOWED: Objek belum di-lock, {action_upper} diizinkan")
            return Response(allowed=True, transaction_id=transaction_id)

        current_lock = lock_table[object_id]

        # Delegate ke validator yang sesuai
        if action_upper == "READ":
            return LockValidator.validate_read_operation(
                object_id, transaction_id, current_lock, verbose
            )

        elif action_upper == "WRITE":
            return LockValidator.validate_write_operation(
                object_id, transaction_id, current_lock, verbose
            )

        else:
            raise ValueError(f"Aksi unknown '{action}'. Gunakan 'read' atau 'write'.")

    @staticmethod
    def can_upgrade_lock(
        object_id: str, transaction_id: int, lock_table: Dict[str, LockEntry]
    ) -> bool:
        if object_id not in lock_table:
            return False

        current_lock = lock_table[object_id]

        return (
            current_lock.lock_type == "read"
            and transaction_id in current_lock.holders
            and len(current_lock.holders) == 1
        )

    @staticmethod
    def has_lock(
        object_id: str,
        transaction_id: int,
        lock_table: Dict[str, LockEntry],
        lock_type: Union[Literal["read", "write"], None] = None,
    ) -> bool:
        if object_id not in lock_table:
            return False

        current_lock = lock_table[object_id]

        # Cek apakah transaksi ada dalam holders
        if transaction_id not in current_lock.holders:
            return False

        # Jika lock_type specified, cek juga tipenya
        if lock_type is not None and current_lock.lock_type != lock_type:
            return False

        return True
