import json
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional


@dataclass
class LogHistoryEntry:
    """Single entry in the log history"""

    transaction_id: int
    operation_type: str
    object_id: str
    old_value: Any
    new_value: Any
    timestamp: datetime = field(default_factory=datetime.now)

    def __repr__(self):
        return (
            f"LogHistory(TX={self.transaction_id}, op={self.operation_type}, "
            f"obj={self.object_id}, old={self.old_value}, new={self.new_value})"
        )


class LogHistoryManager:
    """
    Manages operation history log for Concurrency Control.
    Tracks all operations (including SELECT) in a simpler format than WAL

    LOG_HISTORY Format:
    - type: 'checkpoint' or 'execution'
    - For execution:
      - action: 'insert', 'update', 'delete', 'select'
      - transaction_id
      - table_name
    - For checkpoint:
      - ongoing_transactions (list of active transaction IDs)
    """

    def __init__(self, log_directory: str = "logs"):
        self.log_directory = log_directory
        os.makedirs(self.log_directory, exist_ok=True)
        self.log_file = os.path.join(self.log_directory, "log_history.log")
        print(f"[LogHistory] Using log file: {self.log_file}")

    def log_insert(self, transaction_id: str, table_name: str):
        """Log INSERT operation (simple format)."""

        self._log_operation(transaction_id, "insert", table_name)

    def log_update(self, transaction_id: str, table_name: str):
        """Log UPDATE operation (simple format)."""

        self._log_operation(transaction_id, "update", table_name)

    def log_delete(self, transaction_id: str, table_name: str):
        """Log DELETE operation (simple format)."""

        self._log_operation(transaction_id, "delete", table_name)

    def log_select(self, transaction_id: str, table_name: str):
        """Log SELECT operation (only in log_history, not WAL)."""

        self._log_operation(transaction_id, "select", table_name)

    def log_start(self, transaction_id: str):
        """Log transaction start."""

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "control",
            "action": "start",
            "transaction_id": transaction_id
        }
        self._write_entry(entry)

    def log_commit(self, transaction_id: str):
        """Log transaction commit."""

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "control",
            "action": "commit",
            "transaction_id": transaction_id
        }
        self._write_entry(entry)

    def log_abort(self, transaction_id: str):
        """Log transaction abort."""

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "control",
            "action": "abort",
            "transaction_id": transaction_id
        }
        self._write_entry(entry)

    def log_checkpoint(self, ongoing_transactions: List[str]):
        """
        Log checkpoint with list of ongoing transactions.

        Args:
            ongoing_transactions: List of active transaction IDs
        """

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "checkpoint",
            "ongoing_transactions": ongoing_transactions
        }
        self._write_entry(entry)
        print(
            f"[LogHistory] Checkpoint logged with {len(ongoing_transactions)} ongoing transactions")

    def clear(self, keep_from_transaction: Optional[str] = None):
        if not os.path.exists(self.log_file):
            return

        with open(self.log_file, "r") as f:
            lines = f.readlines()

        if not keep_from_transaction:
            with open(self.log_file, "w") as f:
                f.write("")
            print("[LogHistory] Cleared all entries")
            return

        entries_to_keep = []
        found_transaction = False

        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except:
                continue

            if entry.get("transaction_id") == keep_from_transaction:
                found_transaction = True

            if found_transaction:
                entries_to_keep.append(line)

        with open(self.log_file, "w") as f:
            f.writelines(entries_to_keep)

        cleared_count = len(lines) - len(entries_to_keep)
        print(
            f"[LogHistory] Cleared {cleared_count} entries, kept {len(entries_to_keep)}")

    def _log_operation(self, transaction_id: str, action: str, table_name: str):
        """Log a simple operation (INSERT/UPDATE/DELETE/SELECT)."""

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "execution",
            "action": action,
            "transaction_id": transaction_id,
            "table_name": table_name
        }
        self._write_entry(entry)

    def _write_entry(self, entry: Dict[str, Any]):
        """Write a single entry to log file."""

        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
