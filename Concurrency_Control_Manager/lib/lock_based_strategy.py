from typing import Any, Dict, Set, Union
from dataclasses import dataclass, field

from .strategy_interface import ConcurrencyStrategy, Response
from .lock_validator import LockValidator, LockEntry


class LockBasedStrategy(ConcurrencyStrategy):
    def __init__(self, verbose: bool = True):
        self.lock_table: Dict[str, LockEntry] = {}
        self.validator = LockValidator()
        self.verbose = verbose

    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    def _normalize_action(self, action: str) -> str:
        return action.strip().upper()

    def log_object(self, obj: Any, transaction_id: int, action: str):
        object_id = self._get_object_id(obj)
        action_upper = self._normalize_action(action)

        # STEP 1: Validasi terlebih dahulu menggunakan validator
        response = self.validate_object(obj, transaction_id, action)
        
        if not response.allowed:
            # Jika tidak diizinkan, raise exception
            raise Exception(
                f"Pelanggaran Concurrency: TX {transaction_id} tidak bisa "
                f"{action_upper} pada objek '{object_id}'"
            )

        # STEP 2: Eksekusi lock acquisition (response.allowed == True)
        if action_upper == "WRITE":
            # Cek apakah ini lock upgrade dari READ ke WRITE
            if self.validator.can_upgrade_lock(object_id, transaction_id, self.lock_table):
                if self.verbose:
                    print(f"[LockStrategy] Lock UPGRADE: READ → WRITE pada '{object_id}' untuk TX {transaction_id}")
            
            # Set/update WRITE lock (exclusive)
            self.lock_table[object_id] = LockEntry(
                lock_type="write", 
                holders={transaction_id}
            )
            if self.verbose:
                print(f"[LockStrategy] ✓ WRITE lock acquired: {self.lock_table[object_id]}")

        elif action_upper == "READ":
            # Cek apakah objek belum di-lock sama sekali
            if object_id not in self.lock_table:
                # Buat READ lock baru
                self.lock_table[object_id] = LockEntry(
                    lock_type="read", 
                    holders={transaction_id}
                )
                if self.verbose:
                    print(f"[LockStrategy] ✓ READ lock (new): {self.lock_table[object_id]}")
            
            else:
                current_lock = self.lock_table[object_id]
                
                # Jika sudah ada READ lock, tambahkan ke shared lock
                if current_lock.lock_type == "read":
                    current_lock.holders.add(transaction_id)
                    if self.verbose:
                        print(f"[LockStrategy] ✓ READ lock (shared): {self.lock_table[object_id]}")
                
                # Jika sudah punya WRITE lock, tidak perlu acquire READ lock lagi
                elif current_lock.lock_type == "write" and transaction_id in current_lock.holders:
                    if self.verbose:
                        print(f"[LockStrategy] ℹ TX {transaction_id} sudah punya WRITE lock, READ implicitly allowed")

        else:
            raise ValueError(f"Action unknown '{action}'. Gunakan 'read' atau 'write'.")

    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        object_id = self._get_object_id(obj)
        action_upper = self._normalize_action(action)

        return self.validator.validate_operation(
            object_id=object_id,
            transaction_id=transaction_id,
            action=action_upper,
            lock_table=self.lock_table,
            verbose=self.verbose,
        )

    def end_transaction(self, transaction_id: int):
        released_objects = []
        
        # Cari semua objek yang di-lock oleh transaction_id
        for object_id, lock_entry in list(self.lock_table.items()):
            if transaction_id in lock_entry.holders:
                # Remove transaction dari holders
                lock_entry.holders.discard(transaction_id)
                released_objects.append(object_id)
                
                # Jika tidak ada holder lagi, hapus lock entry
                if not lock_entry.holders:
                    del self.lock_table[object_id]
        
        if self.verbose:
            print(f"[LockStrategy] TX {transaction_id} released locks on: {released_objects}")
            print(f"[LockStrategy] Remaining locks: {self.lock_table}")