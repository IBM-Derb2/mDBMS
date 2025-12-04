from typing import Any, Dict, Set, Union
from dataclasses import dataclass, field
from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
class TimestampEntry:
    """Stores read and write timestamps for an object."""

    read_ts: int = 0
    write_ts: int = 0

    def __repr__(self):
        return f"TimestampEntry(read={self.read_ts}, write={self.write_ts})"


class TimestampBasedStrategy(ConcurrencyStrategy):

    def __init__(self):
        # Key: object_id (string), Value: TimestampEntry
        self.timestamp_table: Dict[str, TimestampEntry] = {}

    # helper buat id
    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    def log_object(self, obj: Any, transaction_id: int, action: str):
        obj_id = self._get_object_id(obj)
        action = action.strip().upper()
        tx_ts = transaction_id

        if obj_id not in self.timestamp_table:
            self.timestamp_table[obj_id] = TimestampEntry()

        entry = self.timestamp_table[obj_id]

        if action == "WRITE":
            entry.write_ts = tx_ts
        elif action == "READ":
            entry.read_ts = max(entry.read_ts, tx_ts)
        else:
            raise ValueError(f"Unknown action {action}. Use 'read' or 'write'.")

    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        obj_id = self._get_object_id(obj)
        action = action.strip().upper()
        tx_ts = transaction_id

        if obj_id not in self.timestamp_table:
            return Response(allowed=True, transaction_id=transaction_id)

        entry = self.timestamp_table[obj_id]

        if action == "READ":
            # Transaction can read if its timestamp >= last write timestamp
            return Response(
                allowed=(tx_ts >= entry.write_ts), transaction_id=transaction_id
            )

        elif action == "WRITE":
            # Transaction can write if its timestamp >= both read and write timestamps
            return Response(
                allowed=(tx_ts >= entry.read_ts and tx_ts >= entry.write_ts),
                transaction_id=transaction_id,
            )

        else:
            raise ValueError(f"Unknown action '{action}'. Use 'read' or 'write'.")

    def end_transaction(self, transaction_id: int):
        pass  # No cleanup needed for timestamp strategy
