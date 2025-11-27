from typing import Any, Dict, Set, Literal, Optional, Callable
from dataclasses import dataclass, field
import time
import threading

from .strategy_interface import ConcurrencyStrategy, Response


@dataclass
class LockEntry:
    lock_type: Literal["read", "write"]
    holders: Set[int] = field(default_factory=set)
    wait_queue: list = field(
        default_factory=list
    )  # List of (tx_id, action) waiting for this lock

    def __repr__(self):
        return f"Lock(type={self.lock_type}, holders={self.holders}, waiting={len(self.wait_queue)})"


class LockBasedStrategy(ConcurrencyStrategy):

    def __init__(self, deadlock_prevention_scheme: str = "wound-wait"):
        """Initialize Lock-Based Strategy with deadlock prevention."""
        self.lock_table: Dict[str, LockEntry] = {}
        self.deadlock_prevention_scheme = deadlock_prevention_scheme
        self.lock_timeout = 5.0  # seconds
        self.tx_manager_ref: Optional[Any] = None
        self.deadlock_callback: Optional[Callable] = None

    def set_transaction_manager(self, tx_manager):
        """Set reference to transaction manager for waiting_for updates."""
        self.tx_manager_ref = tx_manager

    def set_deadlock_callback(self, callback: Callable):
        """Set callback function to trigger deadlock detection."""
        self.deadlock_callback = callback

    def _get_object_id(self, obj: Any) -> str:
        return str(obj)

    def _normalize_action(self, action: str) -> str:
        return action.strip().upper()

    def _get_lock_holders(self, object_id: str) -> Set[int]:
        """Get transaction IDs currently holding locks on the object."""
        if object_id not in self.lock_table:
            return set()
        return self.lock_table[object_id].holders.copy()

    def _should_wait(self, requesting_tx_id: int, holding_tx_ids: Set[int]) -> bool:
        """
        Determine if requesting transaction should wait based on deadlock prevention scheme.

        Wound-Wait: Older transaction wounds (aborts) younger, younger waits for older
        Wait-Die: Older transaction waits, younger dies (aborts)
        """
        if not holding_tx_ids:
            return False

        if self.deadlock_prevention_scheme == "wound-wait":
            # If requester is older (smaller tx_id), it wounds the holders
            # If requester is younger, it waits
            oldest_holder = min(holding_tx_ids)
            if requesting_tx_id < oldest_holder:
                # Requester is older, should wound (abort) the holders
                return False  # Don't wait, will wound
            else:
                # Requester is younger, should wait
                return True

        elif self.deadlock_prevention_scheme == "wait-die":
            # If requester is older, it waits
            # If requester is younger, it dies (aborts)
            youngest_holder = max(holding_tx_ids)
            if requesting_tx_id < youngest_holder:
                # Requester is older, should wait
                return True
            else:
                # Requester is younger, should die
                return False  # Don't wait, will abort

        else:  # timeout mode
            return True  # Always try to wait, rely on timeout

    def _update_waiting_for(self, tx_id: int, waiting_for_tx_id: Optional[int]):
        """Update the waiting_for field in transaction manager."""
        if self.tx_manager_ref:
            tx = self.tx_manager_ref.get_transaction(tx_id)
            if tx:
                tx.waiting_for = waiting_for_tx_id

    def log_object(self, obj: Any, transaction_id: int, action: str):
        obj_id = self._get_object_id(obj)
        action = self._normalize_action(action)

        response = self.validate_object(obj, transaction_id, action)

        if not response.allowed:
            raise Exception(
                f"Concurrency violation: TX {transaction_id} cannot "
                f"{action} on object '{obj_id}'"
            )

        if action == "WRITE":
            if obj_id in self.lock_table:
                current_lock = self.lock_table[obj_id]
                if current_lock.lock_type == "read" and current_lock.holders == {
                    transaction_id
                }:
                    pass  # Lock upgrade from READ to WRITE

            self.lock_table[obj_id] = LockEntry(
                lock_type="write", holders={transaction_id}
            )

        elif action == "READ":
            if obj_id not in self.lock_table:
                self.lock_table[obj_id] = LockEntry(
                    lock_type="read", holders={transaction_id}
                )
            else:
                current_lock = self.lock_table[obj_id]

                if current_lock.lock_type == "read":
                    current_lock.holders.add(transaction_id)
                elif (
                    current_lock.lock_type == "write"
                    and transaction_id in current_lock.holders
                ):
                    pass  # Already have write lock, read implicitly allowed

        else:
            raise ValueError(f"Unknown action '{action}'. Use 'read' or 'write'.")

        # Clear waiting_for since lock was acquired
        self._update_waiting_for(transaction_id, None)

    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        obj_id = self._get_object_id(obj)
        action = self._normalize_action(action)

        if obj_id not in self.lock_table:
            return Response(allowed=True, transaction_id=transaction_id)

        current_lock = self.lock_table[obj_id]

        if action == "READ":
            if current_lock.lock_type == "read":
                return Response(allowed=True, transaction_id=transaction_id)

            elif (
                current_lock.lock_type == "write"
                and transaction_id in current_lock.holders
            ):
                return Response(allowed=True, transaction_id=transaction_id)

            else:
                # Conflict: write lock held by another transaction
                holders = current_lock.holders
                should_wait = self._should_wait(transaction_id, holders)

                if should_wait:
                    oldest_holder = min(holders)
                    self._update_waiting_for(transaction_id, oldest_holder)

                    # Trigger deadlock detection
                    if self.deadlock_callback:
                        self.deadlock_callback()

                return Response(allowed=False, transaction_id=transaction_id)

        elif action == "WRITE":
            if (
                current_lock.lock_type == "write"
                and transaction_id in current_lock.holders
            ):
                return Response(allowed=True, transaction_id=transaction_id)

            elif current_lock.lock_type == "read" and current_lock.holders == {
                transaction_id
            }:
                return Response(allowed=True, transaction_id=transaction_id)

            else:
                # Conflict: lock held by other transaction(s)
                holders = current_lock.holders - {transaction_id}
                if holders:
                    should_wait = self._should_wait(transaction_id, holders)

                    if should_wait:
                        oldest_holder = min(holders)
                        self._update_waiting_for(transaction_id, oldest_holder)

                        # Trigger deadlock detection
                        if self.deadlock_callback:
                            self.deadlock_callback()

                    return Response(allowed=False, transaction_id=transaction_id)
                else:
                    return Response(allowed=True, transaction_id=transaction_id)

        else:
            raise ValueError(f"Unknown action '{action}'. Use 'read' or 'write'.")

    def end_transaction(self, transaction_id: int):
        released = [
            obj_id
            for obj_id, lock in self.lock_table.items()
            if transaction_id in lock.holders
        ]

        for obj_id in released:
            lock = self.lock_table[obj_id]
            lock.holders.discard(transaction_id)

            if not lock.holders:
                del self.lock_table[obj_id]

        # Clear waiting_for
        self._update_waiting_for(transaction_id, None)

    def get_wait_for_graph(self) -> Dict[int, Set[int]]:
        """
        Generate wait-for graph for deadlock detection visualization.
        Returns: Dict mapping transaction_id -> set of transaction_ids it's waiting for
        """
        wait_graph = {}

        if not self.tx_manager_ref:
            return wait_graph

        for tx_id in self.tx_manager_ref.active_transactions:
            tx = self.tx_manager_ref.get_transaction(tx_id)
            if tx and tx.waiting_for is not None:
                wait_graph[tx_id] = {tx.waiting_for}

        return wait_graph

    def print_lock_table(self):
        """Print current lock table for debugging."""
        print("\n" + "=" * 60)
        print("LOCK TABLE")
        print("=" * 60)
        if not self.lock_table:
            print("(empty)")
        else:
            for obj_id, lock in self.lock_table.items():
                print(f"Object '{obj_id}': {lock}")
        print("=" * 60 + "\n")
