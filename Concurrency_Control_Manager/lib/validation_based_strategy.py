from typing import Any, Dict, Set, Union
from dataclasses import dataclass, field
from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
# nyimpen 2 set: apa yg dibaca & apa yg ditulis
class TransactionSetsEntry:
    read_set: Set[str] = field(default_factory=set)
    write_set: Set[str] = field(default_factory=set)
    start_ts: int = 0  # When transaction started its validation phase

    def __repr__(self):
        return (f"Sets(Read={self.read_set}, Write={self.write_set}, TS={self.start_ts})")


class ValidationBasedStrategy(ConcurrencyStrategy):
    """
    Optimistic Concurrency Control (OCC) - Validation-Based Strategy

    Three phases:
    1. READ Phase: Transaction reads data and makes local copies
    2. VALIDATION Phase: Check for conflicts before commit
    3. WRITE Phase: If validation succeeds, write changes to database

    During READ/WRITE operations, all actions are allowed (optimistic).
    Actual validation happens at commit time.
    """

    def __init__(self):
        self.transaction_sets: Dict[int, TransactionSetsEntry] = {}
        self.committed_transactions: Dict[int, TransactionSetsEntry] = {}
        self.transaction_counter = 0  # For assigning validation timestamps
        self.verbose = True

    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    def log_object(self, obj: Any, transaction_id: int, action: str):
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()

        if self.verbose:
            print(f"[ValidationStrategy] TX {transaction_id} me-log '{action_upper}' pada '{object_id}'...")

        if transaction_id not in self.transaction_sets:
            self.transaction_sets[transaction_id] = TransactionSetsEntry()

        entry = self.transaction_sets[transaction_id]

        if action_upper == 'WRITE':
            entry.write_set.add(object_id)
            if self.verbose:
                print(f"    -> Sukses: WRITE log, '{object_id}' ditambah ke write_set TX {transaction_id}")

        elif action_upper == 'READ':
            # Cuma nyatet ke 'read_set' pribadinya dia
            entry.read_set.add(object_id)
            if self.verbose:
                print(f"    -> Sukses: READ log, '{object_id}' ditambah ke read_set TX {transaction_id}")

        else:
            raise ValueError(f"Aksi unkown {action}. Gunakan 'read' atau 'write'.")



    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        object_id = self._get_object_id(obj)
        action_upper = action.strip().upper()

        # Validation-based strategy menggunakan optimistic concurrency control
        # Validasi dilakukan saat commit, bukan saat akses
        # Di fase READ/WRITE, semua aksi diizinkan terlebih dahulu

        if action_upper == 'READ':
            if self.verbose:
                print(f"[ValidationStrategy] Validasi READ pada '{object_id}' untuk TX {transaction_id}: "
                      f"DIIZINKAN (optimistic, akan divalidasi saat commit)")
            return Response(allowed=True, transaction_id=transaction_id)

        elif action_upper == 'WRITE':
            if self.verbose:
                print(f"[ValidationStrategy] Validasi WRITE pada '{object_id}' untuk TX {transaction_id}: "
                      f"DIIZINKAN (optimistic, akan divalidasi saat commit)")
            return Response(allowed=True, transaction_id=transaction_id)

        else:
            raise ValueError(f"Aksi unknown '{action}'. Gunakan 'read' atau 'write'.")

    def validate_for_commit(self, transaction_id: int) -> tuple[bool, list[str]]:
        """
        Perform validation at commit time (OCC validation phase).

        Validation rules:
        1. For each transaction T that committed after this transaction started:
           - Check for write-read conflicts: T.write_set ∩ this.read_set
           - Check for write-write conflicts: T.write_set ∩ this.write_set

        Returns:
            (is_valid, list_of_errors)
        """
        if transaction_id not in self.transaction_sets:
            return (True, [])

        tx_entry = self.transaction_sets[transaction_id]
        errors = []

        if self.verbose:
            print(f"\n[ValidationStrategy] Validating TX {transaction_id} for commit...")
            print(f"  Read set: {tx_entry.read_set}")
            print(f"  Write set: {tx_entry.write_set}")

        # Check conflicts with all committed transactions
        for committed_tx_id, committed_entry in self.committed_transactions.items():
            if committed_tx_id == transaction_id:
                continue

            # Write-Read Conflict:
            # Committed transaction wrote something that current transaction read
            write_read_conflict = committed_entry.write_set.intersection(tx_entry.read_set)
            if write_read_conflict:
                errors.append(
                    f"Write-Read conflict with committed TX {committed_tx_id} "
                    f"on objects: {write_read_conflict}"
                )
                if self.verbose:
                    print(f"  [FAIL] W-R Conflict with TX {committed_tx_id}: {write_read_conflict}")

            # Write-Write Conflict:
            # Committed transaction wrote something that current transaction wants to write
            write_write_conflict = committed_entry.write_set.intersection(tx_entry.write_set)
            if write_write_conflict:
                errors.append(
                    f"Write-Write conflict with committed TX {committed_tx_id} "
                    f"on objects: {write_write_conflict}"
                )
                if self.verbose:
                    print(f"  [FAIL] W-W Conflict with TX {committed_tx_id}: {write_write_conflict}")

        # Also check with active transactions that are in validation phase
        for active_tx_id, active_entry in self.transaction_sets.items():
            if active_tx_id == transaction_id:
                continue

            # If another transaction is also trying to commit, check for conflicts
            # Write-Write conflict with active transactions
            write_write_conflict = active_entry.write_set.intersection(tx_entry.write_set)
            if write_write_conflict:
                # Use transaction_id as tie-breaker: lower ID wins
                if transaction_id > active_tx_id:
                    errors.append(
                        f"Write-Write conflict with active TX {active_tx_id} "
                        f"on objects: {write_write_conflict} (TX {transaction_id} must wait/abort)"
                    )
                    if self.verbose:
                        print(f"  [FAIL] W-W Conflict with active TX {active_tx_id}: {write_write_conflict}")

        is_valid = len(errors) == 0

        if self.verbose:
            if is_valid:
                print(f"  [OK] Validation PASSED for TX {transaction_id}")
            else:
                print(f"  [FAIL] Validation FAILED for TX {transaction_id}")
                for error in errors:
                    print(f"    - {error}")

        return (is_valid, errors)

    def commit_validation(self, transaction_id: int):
        """
        Mark transaction as validated and committed.
        Move from active to committed transactions.
        """
        if transaction_id in self.transaction_sets:
            entry = self.transaction_sets[transaction_id]

            # Assign validation timestamp
            self.transaction_counter += 1
            entry.start_ts = self.transaction_counter

            # Move to committed transactions
            self.committed_transactions[transaction_id] = entry
            del self.transaction_sets[transaction_id]

            if self.verbose:
                print(f"[ValidationStrategy] TX {transaction_id} validated and committed (TS={entry.start_ts})")

    def end_transaction(self, transaction_id: int):
        """Clean up transaction sets."""
        if self.verbose:
            print(f"[ValidationStrategy] TX {transaction_id} selesai")

        # Remove from active transactions if still there
        if transaction_id in self.transaction_sets:
            del self.transaction_sets[transaction_id]

        # Keep committed transactions for a while for validation
        # In production, you might want to garbage collect old committed transactions
        # For now, we keep them to ensure correct validation

    def garbage_collect_committed(self, keep_last_n: int = 100):
        """
        Remove old committed transactions to prevent memory bloat.
        Keep only the most recent N committed transactions.
        """
        if len(self.committed_transactions) > keep_last_n:
            # Sort by timestamp and keep most recent
            sorted_txs = sorted(
                self.committed_transactions.items(),
                key=lambda x: x[1].start_ts,
                reverse=True
            )

            # Keep only recent ones
            self.committed_transactions = dict(sorted_txs[:keep_last_n])

            if self.verbose:
                print(f"[ValidationStrategy] Garbage collected old committed transactions, "
                      f"keeping {keep_last_n} most recent")
