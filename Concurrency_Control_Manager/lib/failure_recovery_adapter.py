from .undo_log import UndoLogEntry
from log_config import ActionType, MockChangeReport  # type: ignore
from log_writer import LogWriter  # type: ignore
import sys
import os
from typing import Any, List, Dict

failure_recovery_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Failure_Recovery")
)
sys.path.append(failure_recovery_path)


class FailureRecoveryAdapter:
    """Bridges Concurrency Control Manager with Failure Recovery logging system."""

    def __init__(self, log_directory: str = "logs"):
        self.log_writer = LogWriter(log_directory=log_directory)
        self.undo_logs: Dict[int, List[UndoLogEntry]] = {}
        self.total_logged_operations = 0
        self.total_rollbacks = 0
        self.storage_manager = None

    def set_storage_manager(self, storage_manager):
        """Set storage manager reference for actual rollback operations."""
        self.storage_manager = storage_manager

    def log_operation(
        self,
        transaction_id: int,
        operation_type: str,
        object_id: str,
        old_value: Any,
        new_value: Any,
    ):
        """Log write operation to both in-memory and Failure Recovery disk."""
        if transaction_id not in self.undo_logs:
            self.undo_logs[transaction_id] = []

        undo_entry = UndoLogEntry(
            transaction_id=transaction_id,
            operation_type=operation_type,
            object_id=object_id,
            old_value=old_value,
            new_value=new_value,
        )
        self.undo_logs[transaction_id].append(undo_entry)
        self.total_logged_operations += 1

        # Write to Failure Recovery log file
        # Note: LogWriter.log_operation requires table, pk, old_data, new_data
        # For now we skip detailed WAL logging since we need proper table/pk info

    def rollback_transaction(self, transaction_id: int) -> List[UndoLogEntry]:
        """Rollback all operations for a transaction."""
        if transaction_id not in self.undo_logs:
            return []

        operations_to_undo = list(reversed(self.undo_logs[transaction_id]))

        for operation in operations_to_undo:
            self._undo_operation(operation)

        # Log ABORT to Failure Recovery
        from log_config import WalAction
        self.log_writer.log_lifecycle(transaction_id, WalAction.ABORT)

        self.total_rollbacks += 1
        return operations_to_undo

    def _undo_operation(self, entry: UndoLogEntry):
        """Undo a single operation by restoring old value to storage."""
        if self.storage_manager:
            self.storage_manager.write_block(
                object_id=entry.object_id,
                old_value=entry.old_value,
                operation_type=entry.operation_type,
                transaction_id=entry.transaction_id,
            )

    def clear_transaction(self, transaction_id: int):
        """Clear undo logs for a transaction after commit or abort."""
        if transaction_id in self.undo_logs:
            del self.undo_logs[transaction_id]

    def log_start(self, transaction_id: int):
        """Log START to Failure Recovery system."""
        from log_config import WalAction
        self.log_writer.log_lifecycle(transaction_id, WalAction.START)

    def log_commit(self, transaction_id: int):
        """Log COMMIT to Failure Recovery system."""
        from log_config import WalAction
        self.log_writer.log_lifecycle(transaction_id, WalAction.COMMIT)

    def get_transaction_logs(self, transaction_id: int) -> List[UndoLogEntry]:
        """Get all undo log entries for a transaction."""
        return self.undo_logs.get(transaction_id, [])

    def has_logs(self, transaction_id: int) -> bool:
        """Check if transaction has any undo logs."""
        return (
            transaction_id in self.undo_logs and len(
                self.undo_logs[transaction_id]) > 0
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
        print("FAILURE RECOVERY ADAPTER STATISTICS")
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

        print(f"\n[FRAdapter] Transaction {transaction_id} Logs:")
        print("-" * 60)

        if not logs:
            print("  (no logs)")
        else:
            for i, entry in enumerate(logs, 1):
                print(
                    f"  {i}. {entry.operation_type}: "
                    f"'{entry.object_id}' | "
                    f"old={entry.old_value} -> new={entry.new_value}"
                )

        print("-" * 60 + "\n")

    def clear_all(self):
        """Clear all undo logs (use with caution!)."""
        self.undo_logs.clear()

    def _parse_object_id(self, object_id: str):
        """Parse object_id to extract table_name and primary_key.

        Format: "table_name:pk_field=pk_value" or "object_id"
        Examples: "products:id=1" -> ("products", {"id": 1})
        """
        try:
            if ":" in object_id:
                table_name, key_part = object_id.split(":", 1)
                if "=" in key_part:
                    key_field, key_value = key_part.split("=", 1)
                    try:
                        key_value = int(key_value)
                    except ValueError:
                        pass
                    return table_name, {key_field: key_value}
                else:
                    return table_name, {"id": key_part}
            else:
                return "data", {"id": object_id}
        except Exception:
            return "data", {"id": object_id}
