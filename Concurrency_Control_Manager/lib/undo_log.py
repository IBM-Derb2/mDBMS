from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OperationType(Enum):
    """Type of operation in undo log."""

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class UndoLogEntry:
    """Single entry in the undo log."""

    transaction_id: int
    operation_type: OperationType
    object_id: str
    old_value: Any  # Previous value before operation
    new_value: Any  # New value after operation
    timestamp: datetime = field(default_factory=datetime.now)

    def __repr__(self):
        return (
            f"UndoLog(TX={self.transaction_id}, op={self.operation_type.value}, "
            f"obj={self.object_id}, old={self.old_value}, new={self.new_value})"
        )


class UndoLogManager:
    """
    Manages undo logs for transaction rollback.

    This component:
    - Records all write operations with their before/after values
    - Provides rollback capability by reversing operations
    - Maintains logs per transaction
    - Cleans up logs after commit/abort completion
    """

    def __init__(self):
        self.undo_logs: Dict[int, List[UndoLogEntry]] = {}
        self.total_logged_operations = 0
        self.total_rollbacks = 0

    def log_operation(
        self,
        transaction_id: int,
        operation_type: OperationType,
        object_id: str,
        old_value: Any,
        new_value: Any,
    ):
        """Log a write operation for potential rollback."""
        if transaction_id not in self.undo_logs:
            self.undo_logs[transaction_id] = []

        entry = UndoLogEntry(
            transaction_id=transaction_id,
            operation_type=operation_type,
            object_id=object_id,
            old_value=old_value,
            new_value=new_value,
        )

        self.undo_logs[transaction_id].append(entry)
        self.total_logged_operations += 1

    def rollback_transaction(self, transaction_id: int) -> List[UndoLogEntry]:
        """Rollback all operations for a transaction."""
        if transaction_id not in self.undo_logs:
            return []

        logs = list(reversed(self.undo_logs[transaction_id]))

        for entry in logs:
            self._undo_operation(entry)

        self.total_rollbacks += 1
        return logs

    def _undo_operation(self, entry: UndoLogEntry):
        """Undo a single operation."""
        # In a real system, this would interact with Storage Manager
        pass

    def commit_transaction(self, transaction_id: int):
        """Clean up undo logs after successful commit."""
        if transaction_id in self.undo_logs:
            del self.undo_logs[transaction_id]

    def abort_transaction(self, transaction_id: int):
        """Rollback and clean up undo logs after abort."""
        self.rollback_transaction(transaction_id)

        if transaction_id in self.undo_logs:
            del self.undo_logs[transaction_id]

    def get_transaction_logs(self, transaction_id: int) -> List[UndoLogEntry]:
        """Get all undo log entries for a transaction."""
        return self.undo_logs.get(transaction_id, [])

    def has_logs(self, transaction_id: int) -> bool:
        """Check if transaction has any undo logs."""
        return (
            transaction_id in self.undo_logs and len(self.undo_logs[transaction_id]) > 0
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get undo log statistics."""
        active_transactions = len(self.undo_logs)
        total_pending_logs = sum(len(logs) for logs in self.undo_logs.values())

        return {
            "total_logged_operations": self.total_logged_operations,
            "total_rollbacks": self.total_rollbacks,
            "active_transactions_with_logs": active_transactions,
            "pending_undo_logs": total_pending_logs,
        }

    def print_statistics(self):
        """Print undo log statistics."""
        stats = self.get_statistics()
        print("\n" + "=" * 60)
        print("UNDO LOG STATISTICS")
        print("=" * 60)
        print(f"Total Logged Operations: {stats['total_logged_operations']}")
        print(f"Total Rollbacks Performed: {stats['total_rollbacks']}")
        print(
            f"Active Transactions with Logs: {stats['active_transactions_with_logs']}"
        )
        print(f"Pending Undo Logs: {stats['pending_undo_logs']}")
        print("=" * 60 + "\n")

    def print_transaction_logs(self, transaction_id: int):
        """Print all undo logs for a specific transaction."""
        logs = self.get_transaction_logs(transaction_id)

        print(f"\n[UndoLog] Transaction {transaction_id} Logs:")
        print("-" * 60)

        if not logs:
            print("  (no logs)")
        else:
            for i, entry in enumerate(logs, 1):
                print(
                    f"  {i}. {entry.operation_type.value.upper()}: "
                    f"'{entry.object_id}' | "
                    f"old={entry.old_value} -> new={entry.new_value}"
                )

        print("-" * 60 + "\n")

    def clear_all(self):
        """Clear all undo logs (use with caution!)."""
        self.undo_logs.clear()
