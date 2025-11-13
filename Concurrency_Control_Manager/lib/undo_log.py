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
        return (f"UndoLog(TX={self.transaction_id}, op={self.operation_type.value}, "
                f"obj={self.object_id}, old={self.old_value}, new={self.new_value})")


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
        # Transaction ID -> List of undo log entries
        self.undo_logs: Dict[int, List[UndoLogEntry]] = {}
        # Statistics
        self.total_logged_operations = 0
        self.total_rollbacks = 0
        self.verbose = True

    def log_operation(
        self,
        transaction_id: int,
        operation_type: OperationType,
        object_id: str,
        old_value: Any,
        new_value: Any
    ):
        """
        Log a write operation for potential rollback.

        Args:
            transaction_id: ID of the transaction performing the operation
            operation_type: Type of operation (INSERT, UPDATE, DELETE)
            object_id: Identifier of the object being modified
            old_value: Value before the operation (None for INSERT)
            new_value: Value after the operation (None for DELETE)
        """
        if transaction_id not in self.undo_logs:
            self.undo_logs[transaction_id] = []

        entry = UndoLogEntry(
            transaction_id=transaction_id,
            operation_type=operation_type,
            object_id=object_id,
            old_value=old_value,
            new_value=new_value
        )

        self.undo_logs[transaction_id].append(entry)
        self.total_logged_operations += 1

        if self.verbose:
            print(f"[UndoLog] Logged {operation_type.value} on '{object_id}' for TX {transaction_id}")

    def rollback_transaction(self, transaction_id: int) -> List[UndoLogEntry]:
        """
        Rollback all operations for a transaction.

        Returns:
            List of undo log entries that were rolled back (in reverse order)
        """
        if transaction_id not in self.undo_logs:
            if self.verbose:
                print(f"[UndoLog] No undo logs found for TX {transaction_id}")
            return []

        # Get logs in reverse order (most recent first)
        logs = list(reversed(self.undo_logs[transaction_id]))

        if self.verbose:
            print(f"\n[UndoLog] Rolling back TX {transaction_id} ({len(logs)} operations)...")

        for entry in logs:
            self._undo_operation(entry)

        self.total_rollbacks += 1

        if self.verbose:
            print(f"[UndoLog] [OK] TX {transaction_id} rolled back successfully\n")

        return logs

    def _undo_operation(self, entry: UndoLogEntry):
        """
        Undo a single operation.

        For INSERT: Delete the inserted value
        For UPDATE: Restore old value
        For DELETE: Restore deleted value
        """
        if self.verbose:
            op_name = entry.operation_type.value.upper()
            print(f"  [UndoLog] Undoing {op_name} on '{entry.object_id}'")

        # In a real system, this would interact with Storage Manager
        # For now, we just log the undo action
        if entry.operation_type == OperationType.INSERT:
            # Undo INSERT by deleting
            if self.verbose:
                print(f"    -> Would DELETE '{entry.object_id}' (undo INSERT)")

        elif entry.operation_type == OperationType.UPDATE:
            # Undo UPDATE by restoring old value
            if self.verbose:
                print(f"    -> Would RESTORE '{entry.object_id}' to old value: {entry.old_value}")

        elif entry.operation_type == OperationType.DELETE:
            # Undo DELETE by restoring deleted value
            if self.verbose:
                print(f"    -> Would RESTORE deleted '{entry.object_id}': {entry.old_value}")

    def commit_transaction(self, transaction_id: int):
        """
        Clean up undo logs after successful commit.
        Once committed, we no longer need the undo information.
        """
        if transaction_id in self.undo_logs:
            log_count = len(self.undo_logs[transaction_id])
            del self.undo_logs[transaction_id]

            if self.verbose:
                print(f"[UndoLog] Cleared {log_count} undo logs for committed TX {transaction_id}")

    def abort_transaction(self, transaction_id: int):
        """
        Rollback and clean up undo logs after abort.
        """
        self.rollback_transaction(transaction_id)

        # Clean up logs after rollback
        if transaction_id in self.undo_logs:
            del self.undo_logs[transaction_id]

    def get_transaction_logs(self, transaction_id: int) -> List[UndoLogEntry]:
        """Get all undo log entries for a transaction."""
        return self.undo_logs.get(transaction_id, [])

    def has_logs(self, transaction_id: int) -> bool:
        """Check if transaction has any undo logs."""
        return transaction_id in self.undo_logs and len(self.undo_logs[transaction_id]) > 0

    def get_statistics(self) -> Dict[str, Any]:
        """Get undo log statistics."""
        active_transactions = len(self.undo_logs)
        total_pending_logs = sum(len(logs) for logs in self.undo_logs.values())

        return {
            'total_logged_operations': self.total_logged_operations,
            'total_rollbacks': self.total_rollbacks,
            'active_transactions_with_logs': active_transactions,
            'pending_undo_logs': total_pending_logs
        }

    def print_statistics(self):
        """Print undo log statistics."""
        stats = self.get_statistics()
        print("\n" + "="*60)
        print("UNDO LOG STATISTICS")
        print("="*60)
        print(f"Total Logged Operations: {stats['total_logged_operations']}")
        print(f"Total Rollbacks Performed: {stats['total_rollbacks']}")
        print(f"Active Transactions with Logs: {stats['active_transactions_with_logs']}")
        print(f"Pending Undo Logs: {stats['pending_undo_logs']}")
        print("="*60 + "\n")

    def print_transaction_logs(self, transaction_id: int):
        """Print all undo logs for a specific transaction."""
        logs = self.get_transaction_logs(transaction_id)

        print(f"\n[UndoLog] Transaction {transaction_id} Logs:")
        print("-" * 60)

        if not logs:
            print("  (no logs)")
        else:
            for i, entry in enumerate(logs, 1):
                print(f"  {i}. {entry.operation_type.value.upper()}: "
                      f"'{entry.object_id}' | "
                      f"old={entry.old_value} -> new={entry.new_value}")

        print("-" * 60 + "\n")

    def clear_all(self):
        """Clear all undo logs (use with caution!)."""
        self.undo_logs.clear()
        if self.verbose:
            print("[UndoLog] All undo logs cleared")
