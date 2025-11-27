from typing import Any, Dict, Set, Union
from dataclasses import dataclass, field
from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
class TransactionSetsEntry:
    """Stores read and write sets for a transaction."""

    read_set: Set[str] = field(default_factory=set)
    write_set: Set[str] = field(default_factory=set)
    start_ts: int = 0

    def __repr__(self):
        return f"TransactionSets(read={self.read_set}, write={self.write_set}, ts={self.start_ts})"


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
        self.transaction_counter = 0

    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    def log_object(self, obj: Any, transaction_id: int, action: str):
        obj_id = self._get_object_id(obj)
        action = action.strip().upper()

        if transaction_id not in self.transaction_sets:
            self.transaction_sets[transaction_id] = TransactionSetsEntry()

        entry = self.transaction_sets[transaction_id]

        if action == "WRITE":
            entry.write_set.add(obj_id)
        elif action == "READ":
            entry.read_set.add(obj_id)
        else:
            raise ValueError(f"Unknown action {action}. Use 'read' or 'write'.")

    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        # Optimistic: validation happens at commit, not during access
        return Response(allowed=True, transaction_id=transaction_id)

    def validate_for_commit(self, transaction_id: int) -> tuple[bool, list[str]]:
        """Perform validation at commit time (OCC validation phase)."""
        if transaction_id not in self.transaction_sets:
            return (True, [])

        tx_entry = self.transaction_sets[transaction_id]
        errors = []

        # Check conflicts with all committed transactions
        for committed_id, committed_entry in self.committed_transactions.items():
            if committed_id == transaction_id:
                continue

            # Write-Read Conflict
            wr_conflict = committed_entry.write_set.intersection(tx_entry.read_set)
            if wr_conflict:
                errors.append(
                    f"Write-Read conflict: Committed TX {committed_id} wrote objects {wr_conflict} that TX {transaction_id} read"
                )

            # Write-Write Conflict
            ww_conflict = committed_entry.write_set.intersection(tx_entry.write_set)
            if ww_conflict:
                errors.append(
                    f"Write-Write conflict: Both TX {committed_id} and TX {transaction_id} wrote to: {ww_conflict}"
                )

        # Check with active transactions
        for active_id, active_entry in self.transaction_sets.items():
            if active_id == transaction_id:
                continue

            ww_conflict = active_entry.write_set.intersection(tx_entry.write_set)
            if ww_conflict and transaction_id > active_id:
                errors.append(
                    f"Write-Write conflict with active TX {active_id} "
                    f"on objects: {ww_conflict} (TX {transaction_id} must wait/abort)"
                )

        return (len(errors) == 0, errors)

    def commit_validation(self, transaction_id: int):
        """Mark transaction as validated and committed."""
        if transaction_id in self.transaction_sets:
            entry = self.transaction_sets[transaction_id]

            self.transaction_counter += 1
            entry.start_ts = self.transaction_counter

            self.committed_transactions[transaction_id] = entry
            del self.transaction_sets[transaction_id]

    def end_transaction(self, transaction_id: int):
        """Clean up transaction sets."""
        if transaction_id in self.transaction_sets:
            del self.transaction_sets[transaction_id]

    def garbage_collect_committed(self, keep_last_n: int = 100):
        """Remove old committed transactions to prevent memory bloat."""
        if len(self.committed_transactions) > keep_last_n:
            sorted_txs = sorted(
                self.committed_transactions.items(),
                key=lambda x: x[1].start_ts,
                reverse=True,
            )
            self.committed_transactions = dict(sorted_txs[:keep_last_n])
