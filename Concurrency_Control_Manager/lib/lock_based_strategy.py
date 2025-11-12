from typing import Any, Dict, Set, Literal
from dataclasses import dataclass, field

from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
class LockEntry:
    lock_type: Literal["read", "write"]
    holders: Set[int] = field(default_factory=set)

    def __repr__(self):
        return f"Lock(type={self.lock_type}, holders={self.holders})"


class LockBasedStrategy(ConcurrencyStrategy):

    def __init__(self):
        self.lock_table: Dict[str, LockEntry] = {}
        self.verbose = True

    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    def _normalize_action(self, action: str) -> str:
        return action.strip().upper()

    def log_object(self, obj: Any, transaction_id: int, action: str):
        object_id = self._get_object_id(obj)
        action_upper = self._normalize_action(action)

        response = self.validate_object(obj, transaction_id, action)

        if not response.allowed:
            raise Exception(
                f"Pelanggaran Concurrency: TX {transaction_id} tidak bisa "
                f"{action_upper} pada objek '{object_id}'"
            )

        if action_upper == "WRITE":
            if object_id in self.lock_table:
                current_lock = self.lock_table[object_id]
                if current_lock.lock_type == "read" and current_lock.holders == {
                    transaction_id
                }:
                    if self.verbose:
                        print(
                            f"[LockStrategy] Lock UPGRADE: READ → WRITE pada '{object_id}' untuk TX {transaction_id}"
                        )

            self.lock_table[object_id] = LockEntry(
                lock_type="write", holders={transaction_id}
            )
            if self.verbose:
                print(
                    f"[LockStrategy] ✓ WRITE lock acquired: {self.lock_table[object_id]}"
                )

        elif action_upper == "READ":
            if object_id not in self.lock_table:
                self.lock_table[object_id] = LockEntry(
                    lock_type="read", holders={transaction_id}
                )
                if self.verbose:
                    print(
                        f"[LockStrategy] ✓ READ lock (new): {self.lock_table[object_id]}"
                    )
            else:
                current_lock = self.lock_table[object_id]

                if current_lock.lock_type == "read":
                    current_lock.holders.add(transaction_id)
                    if self.verbose:
                        print(
                            f"[LockStrategy] ✓ READ lock (shared): {self.lock_table[object_id]}"
                        )

                elif (
                    current_lock.lock_type == "write"
                    and transaction_id in current_lock.holders
                ):
                    if self.verbose:
                        print(
                            f"[LockStrategy] ℹ TX {transaction_id} sudah punya WRITE lock, READ implicitly allowed"
                        )

        else:
            raise ValueError(f"Action unknown '{action}'. Gunakan 'read' atau 'write'.")

    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        object_id = self._get_object_id(obj)
        action_upper = self._normalize_action(action)

        if object_id not in self.lock_table:
            if self.verbose:
                print(
                    f"[LockStrategy] Validasi '{action}' pada '{obj}' untuk TX {transaction_id}: DIIZINKAN (belum ada lock)"
                )
            return Response(allowed=True, transaction_id=transaction_id)

        current_lock = self.lock_table[object_id]

        if action_upper == "READ":
            if current_lock.lock_type == "read":
                if self.verbose:
                    print(
                        f"[LockStrategy] Validasi READ pada '{obj}' untuk TX {transaction_id}: DIIZINKAN (shared read lock)"
                    )
                return Response(allowed=True, transaction_id=transaction_id)

            elif (
                current_lock.lock_type == "write"
                and transaction_id in current_lock.holders
            ):
                if self.verbose:
                    print(
                        f"[LockStrategy] Validasi READ pada '{obj}' untuk TX {transaction_id}: DIIZINKAN (pemilik write lock)"
                    )
                return Response(allowed=True, transaction_id=transaction_id)

            else:
                if self.verbose:
                    print(
                        f"[LockStrategy] Validasi READ pada '{obj}' untuk TX {transaction_id}: DITOLAK (write lock oleh {current_lock.holders})"
                    )
                return Response(allowed=False, transaction_id=transaction_id)

        elif action_upper == "WRITE":
            if (
                current_lock.lock_type == "write"
                and transaction_id in current_lock.holders
            ):
                if self.verbose:
                    print(
                        f"[LockStrategy] Validasi WRITE pada '{obj}' untuk TX {transaction_id}: DIIZINKAN (sudah pemilik write lock)"
                    )
                return Response(allowed=True, transaction_id=transaction_id)

            elif current_lock.lock_type == "read" and current_lock.holders == {
                transaction_id
            }:
                if self.verbose:
                    print(
                        f"[LockStrategy] Validasi WRITE pada '{obj}' untuk TX {transaction_id}: DIIZINKAN (lock upgrade dari read ke write)"
                    )
                return Response(allowed=True, transaction_id=transaction_id)

            else:
                if self.verbose:
                    if current_lock.lock_type == "read":
                        print(
                            f"[LockStrategy] Validasi WRITE pada '{obj}' untuk TX {transaction_id}: DITOLAK (read lock oleh {current_lock.holders})"
                        )
                    else:
                        print(
                            f"[LockStrategy] Validasi WRITE pada '{obj}' untuk TX {transaction_id}: DITOLAK (write lock oleh {current_lock.holders})"
                        )
                return Response(allowed=False, transaction_id=transaction_id)

        else:
            raise ValueError(f"Action unknown '{action}'. Gunakan 'read' atau 'write'.")

    def end_transaction(self, transaction_id: int):
        released_objects = [
            obj_id
            for obj_id, lock in self.lock_table.items()
            if transaction_id in lock.holders
        ]

        for obj_id in released_objects:
            lock = self.lock_table[obj_id]
            lock.holders.discard(transaction_id)

            if not lock.holders:
                del self.lock_table[obj_id]

        if self.verbose:
            print(
                f"[LockStrategy] TX {transaction_id} released locks on: {released_objects}"
            )
            print(f"[LockStrategy] Remaining locks: {dict(self.lock_table)}")
