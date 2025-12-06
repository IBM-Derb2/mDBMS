import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Union, Iterator
from Failure_Recovery.frm_types import LogEntry
from Failure_Recovery.frm_types import RecoverCriteria


class WALManager:
    """
    Manages Write-Ahead Log (WAL) for recovery and rollback.

    WAL Format:
    - type: 'checkpoint' or 'execution'
    - For execution:
      - action: 'insert', 'update', 'delete', 'start', 'commit', 'abort'
      - transaction_id (int)
      - tablename (lowercase, no underscore)
      - pk_value (primary key dict)
      - record_before (old_data for UPDATE/DELETE)
      - record_after (new_data for INSERT/UPDATE)
    - For checkpoint:
      - ongoing_transactions (list of active transaction IDs)
    """

    def __init__(self, log_directory: str = "logs"):
        self.log_directory = log_directory
        os.makedirs(self.log_directory, exist_ok=True)
        self.wal_file = os.path.join(self.log_directory, "wal.log")
        self.current_log_file = self.wal_file
        print(f"[WAL] Using WAL file: {self.wal_file}")

    def write_to_file(self, content: str):
        """Write string to file (low-level)"""

        with open(self.wal_file, "a") as f:
            f.write(content + "\n")

    def log_lifecycle(self, tx_id: int, action: str):
        """Log START, COMMIT, ABORT"""

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "execution",
            "action": action if isinstance(action, str) else action.value,
            "transaction_id": tx_id
        }
        self.write_to_file(json.dumps(entry))

    def log_operation(self, tx_id: int, table: str, pk: Any,
                      old_data: dict, new_data: dict):
        """Log INSERT, UPDATE, DELETE (Auto-detect action)"""

        if old_data is None and new_data is not None:
            action_str = "insert"
        elif old_data is not None and new_data is None:
            action_str = "delete"
        elif old_data is not None and new_data is not None:
            action_str = "update"
        else:
            return

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "execution",
            "action": action_str,
            "transaction_id": tx_id,
            "tablename": table,
            "pk_value": pk,
            "record_before": old_data,
            "record_after": new_data
        }
        self.write_to_file(json.dumps(entry))

    def log_insert(self, transaction_id: Union[int, str], table_name: str,
                   pk_value: Dict[str, Any], record_inserted: Dict[str, Any]):
        """
        Log INSERT operation.

        Args:
            transaction_id: Transaction ID (int or str)
            table_name: Table name
            pk_value: Primary key dict
            record_inserted: The complete row that was inserted
        """

        tx_id = int(transaction_id) if isinstance(
            transaction_id, str) else transaction_id

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "execution",
            "action": "insert",
            "transaction_id": tx_id,
            "tablename": table_name,
            "pk_value": pk_value,
            "record_before": None,
            "record_after": record_inserted
        }
        self._write_entry(entry)

    def log_update(self, transaction_id: Union[int, str], table_name: str,
                   pk_value: Dict[str, Any], record_before: Dict[str, Any],
                   record_after: Dict[str, Any]):
        """
        Log UPDATE operation.

        Args:
            transaction_id: Transaction ID (int or str)
            table_name: Table name
            pk_value: Primary key dict
            record_before: Old row data
            record_after: New row data
        """

        tx_id = int(transaction_id) if isinstance(
            transaction_id, str) else transaction_id

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "execution",
            "action": "update",
            "transaction_id": tx_id,
            "tablename": table_name,
            "pk_value": pk_value,
            "record_before": record_before,
            "record_after": record_after
        }
        self._write_entry(entry)

    def log_delete(self, transaction_id: Union[int, str], table_name: str,
                   pk_value: Dict[str, Any], record_deleted: Dict[str, Any]):
        """
        Log DELETE operation.

        Args:
            transaction_id: Transaction ID (int or str)
            table_name: Table name
            pk_value: Primary key dict
            record_deleted: The complete row that was deleted
        """

        tx_id = int(transaction_id) if isinstance(
            transaction_id, str) else transaction_id

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "execution",
            "action": "delete",
            "transaction_id": tx_id,
            "tablename": table_name,
            "pk_value": pk_value,
            "record_before": record_deleted,
            "record_after": None
        }
        self._write_entry(entry)

    def log_compensation(self, tx_id: int, original_action: str, table: str, pk: Any, restored_data: dict):
        """Log CLR (Compensation Log Record) during undo"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "execution",
            "action": "compensation",
            "original_action": original_action,
            "transaction_id": tx_id,
            "tablename": table,
            "pk_value": pk,
            "record_before": None,
            "record_after": restored_data
        }
        self.write_to_file(json.dumps(entry))

    def log_checkpoint(self, ongoing_transactions: List[Union[int, str]]):
        """
        Log checkpoint with list of ongoing transactions.

        Args:
            ongoing_transactions: List of active transaction IDs
        """

        # Transaction IDs are strings in format: '127.0.0.1:port-timestamp-counter'
        tx_ids = [str(tx) for tx in ongoing_transactions]

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "checkpoint",
            "ongoing_transactions": tx_ids
        }
        self._write_entry(entry)
        print(
            f"[WAL] Checkpoint logged with {len(tx_ids)} ongoing transactions")

    def clear_wal_before_oldest_transaction(self, ongoing_transactions: List[Union[int, str]]):
        """
        Clear WAL entries that are no longer needed for recovery.
        Keep only entries for ongoing transactions and the most recent checkpoint.

        Args:
            ongoing_transactions: List of active transaction IDs
        """

        if not ongoing_transactions:
            print("[WAL Clear] No ongoing transactions, clearing entire WAL")
            self.clear_entire_wal()
            return

        ongoing_tx_set = set(str(tx) if isinstance(
            tx, str) else str(tx) for tx in ongoing_transactions)
        oldest_tx_id = min(ongoing_tx_set)
        print(f"[WAL Clear] Oldest ongoing transaction: {oldest_tx_id}")
        print(f"[WAL Clear] Ongoing transactions: {sorted(ongoing_tx_set)}")

        if not os.path.exists(self.wal_file):
            print("[WAL Clear] No log file exists")
            return

        entries_to_keep = []
        oldest_tx_start_found = False
        latest_checkpoint = None

        with open(self.wal_file, 'r') as f:
            lines = f.readlines()

        for line in lines:
            try:
                entry = json.loads(line.strip())
                if entry.get('type') == 'checkpoint':
                    latest_checkpoint = line
            except json.JSONDecodeError:
                continue

        for line in lines:
            try:
                entry = json.loads(line.strip())
                tx_id = entry.get('transaction_id')
                action = entry.get('action')
                entry_type = entry.get('type')

                if entry_type == 'checkpoint' and line == latest_checkpoint:
                    entries_to_keep.append(line)
                    print(f"[WAL Clear] Keeping most recent checkpoint")
                    continue

                if (tx_id == oldest_tx_id and action == 'start'):
                    oldest_tx_start_found = True
                    print(
                        f"[WAL Clear] Found START of oldest TX {oldest_tx_id}")

                if oldest_tx_start_found and tx_id in ongoing_tx_set:
                    entries_to_keep.append(line)

            except json.JSONDecodeError:
                continue

        with open(self.wal_file, 'w') as f:
            f.writelines(entries_to_keep)

        cleared_count = len(lines) - len(entries_to_keep)
        print(f"[WAL Clear] Cleared {cleared_count} entries")
        print(
            f"[WAL Clear] Kept {len(entries_to_keep)} entries (checkpoint + ongoing transactions)")

    def clear_entire_wal(self):
        """Clear the entire WAL file"""

        if os.path.exists(self.wal_file):
            with open(self.wal_file, 'w') as f:
                f.write('')
            print("[WAL Clear] Entire WAL cleared")
        else:
            print("[WAL Clear] No WAL file to clear")

    def clear(self, keep_from_transaction: Optional[Union[int, str]] = None):
        """
        Clear WAL entries up to (but not including) the specified transaction.

        Args:
            keep_from_transaction: Transaction ID to keep from (clear everything before this)
        """

        if not os.path.exists(self.wal_file):
            return

        with open(self.wal_file, "r") as f:
            lines = f.readlines()

        if not keep_from_transaction:
            with open(self.wal_file, "w") as f:
                f.write("")
            print("[WAL] Cleared all entries")
            return

        keep_tx = int(keep_from_transaction) if isinstance(
            keep_from_transaction, str) else keep_from_transaction

        entries_to_keep = []
        found_transaction = False

        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                tx_id = entry.get("transaction_id")

                if tx_id == keep_tx:
                    found_transaction = True

                if found_transaction:
                    entries_to_keep.append(line)
            except (json.JSONDecodeError, ValueError, TypeError):
                continue

        with open(self.wal_file, "w") as f:
            f.writelines(entries_to_keep)

        cleared_count = len(lines) - len(entries_to_keep)
        print(
            f"[WAL] Cleared {cleared_count} entries, kept {len(entries_to_keep)}")

    def _write_entry(self, entry: Dict[str, Any]):
        """Write a single entry to WAL file."""

        with open(self.wal_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _get_active_logfile(self) -> str:
        """Get active log file path (for compatibility)"""

        return self.wal_file

    def _iter_file_backward(self, path: str, buf_size: int = 4096) -> Iterator[str]:
        """Read file backwards line by line without loading entire file"""

        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_pos = f.tell()
            remainder = b""
            while file_pos > 0:
                read_size = min(buf_size, file_pos)
                file_pos -= read_size
                f.seek(file_pos)
                chunk = f.read(read_size)
                parts = chunk + remainder
                lines = parts.split(b"\n")
                remainder = lines[0]
                for line in reversed(lines[1:]):
                    yield line.decode("utf-8", "replace")
            if remainder:
                yield remainder.decode("utf-8", "replace")

    def _sorted_log_files_desc(self) -> List[str]:
        """Get list of log files sorted in descending order"""

        if not os.path.exists(self.log_directory):
            return []

        wal_file = os.path.join(self.log_directory, "wal.log")
        if os.path.exists(wal_file):
            return [wal_file]

        files = [f for f in os.listdir(
            self.log_directory) if f.startswith("logfile_")]
        files.sort(reverse=True)
        return [os.path.join(self.log_directory, f) for f in files]

    def _parse_line(self, line: str):
        """Parse a log line into LogEntry"""

        try:

            d: Dict[str, Any] = json.loads(line)
            ts = datetime.fromisoformat(
                d["timestamp"]) if "timestamp" in d else datetime.now()

            # Handle both int and string transaction IDs
            tx_id = d.get("transaction_id", -1)
            if isinstance(tx_id, str):
                # Keep as string (IP-based transaction IDs)
                pass
            elif isinstance(tx_id, int):
                # Already an int
                pass
            else:
                tx_id = -1

            return LogEntry(
                timestamp=ts,
                transaction_id=tx_id,
                action=d.get("action"),
                table_name=d.get("tablename"),
                pk_value=d.get("pk_value"),
                old_data=d.get("record_before"),
                new_data=d.get("record_after"),
                raw_log=d,
            )
        except Exception as e:
            print(f"[WAL Debug] Failed to parse line: {e}")
            return None

    def iter_backward(self, criteria=None) -> Iterator:
        """
        Iterate log entries backward until reaching RecoverCriteria

        Args:
            criteria: RecoverCriteria object (optional)

        Yields:
            LogEntry objects
        """

        if criteria is None:
            criteria = RecoverCriteria()

        for filepath in self._sorted_log_files_desc():
            for line in self._iter_file_backward(filepath):
                entry = self._parse_line(line.strip())
                if not entry:
                    continue

                if criteria.timestamp and entry.timestamp < criteria.timestamp:
                    return

                yield entry

                # Stop at START (case-insensitive check)
                if criteria.transaction_id and entry.transaction_id == criteria.transaction_id and entry.action.lower() == "start":
                    return
