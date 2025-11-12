from enum import Enum
from typing import Dict, Set, Optional, List
from dataclasses import dataclass, field
from datetime import datetime


class TransactionStatus(Enum):
    ACTIVE = "active"
    PARTIALLY_COMMITTED = "partially_committed"
    COMMITTED = "committed"
    FAILED = "failed"
    ABORTED = "aborted"
    TERMINATED = "terminated"


@dataclass
class Operation:
    operation_type: str
    object_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    value: Optional[any] = None


@dataclass
class Transaction:
    transaction_id: int
    status: TransactionStatus = TransactionStatus.ACTIVE
    start_time: datetime = field(default_factory=datetime.now)
    operations: List[Operation] = field(default_factory=list)
    read_set: Set[str] = field(default_factory=set)
    write_set: Set[str] = field(default_factory=set)
    waiting_for: Optional[int] = None
    commit_time: Optional[datetime] = None
    abort_time: Optional[datetime] = None

    def add_operation(self, op_type: str, obj_id: str, value=None):
        op = Operation(operation_type=op_type, object_id=obj_id, value=value)
        self.operations.append(op)

        if op_type.lower() == "read":
            self.read_set.add(obj_id)
        elif op_type.lower() == "write":
            self.write_set.add(obj_id)

    def get_accessed_objects(self) -> Set[str]:
        return self.read_set.union(self.write_set)

    def can_commit(self) -> bool:
        return self.status == TransactionStatus.PARTIALLY_COMMITTED

    def can_abort(self) -> bool:
        return self.status in [TransactionStatus.ACTIVE, TransactionStatus.FAILED]

    def __repr__(self):
        return (
            f"Transaction(id={self.transaction_id}, "
            f"status={self.status.value}, "
            f"operations={len(self.operations)}, "
            f"read_set={self.read_set}, "
            f"write_set={self.write_set})"
        )


class TransactionManager:
    def __init__(self):
        self.transactions: Dict[int, Transaction] = {}
        self.active_transactions: Set[int] = set()
        self.committed_transactions: Set[int] = set()
        self.aborted_transactions: Set[int] = set()

    def create_transaction(self, transaction_id: int) -> Transaction:
        if transaction_id in self.transactions:
            raise ValueError(f"Transaction {transaction_id} sudah ada!")

        tx = Transaction(transaction_id=transaction_id)
        self.transactions[transaction_id] = tx
        self.active_transactions.add(transaction_id)

        print(
            f"[TxManager] TX {transaction_id} dibuat dengan status: {tx.status.value}"
        )
        return tx

    def get_transaction(self, transaction_id: int) -> Optional[Transaction]:
        return self.transactions.get(transaction_id)

    def mark_partially_committed(self, transaction_id: int):
        tx = self.transactions.get(transaction_id)
        if not tx:
            raise ValueError(f"Transaction {transaction_id} tidak ditemukan!")

        if tx.status != TransactionStatus.ACTIVE:
            raise ValueError(
                f"TX {transaction_id} tidak bisa partially committed. "
                f"Status saat ini: {tx.status.value}"
            )

        tx.status = TransactionStatus.PARTIALLY_COMMITTED
        print(f"[TxManager] TX {transaction_id} → PARTIALLY_COMMITTED")

    def commit_transaction(self, transaction_id: int):
        tx = self.transactions.get(transaction_id)
        if not tx:
            raise ValueError(f"Transaction {transaction_id} tidak ditemukan!")

        if tx.status == TransactionStatus.ACTIVE:
            self.mark_partially_committed(transaction_id)

        if not tx.can_commit():
            raise ValueError(
                f"TX {transaction_id} tidak bisa di-commit. "
                f"Status: {tx.status.value}"
            )

        tx.status = TransactionStatus.COMMITTED
        tx.commit_time = datetime.now()

        if transaction_id in self.active_transactions:
            self.active_transactions.remove(transaction_id)
        self.committed_transactions.add(transaction_id)

        print(f"[TxManager] ✓ TX {transaction_id} COMMITTED")

    def fail_transaction(self, transaction_id: int, reason: str = "Unknown"):
        tx = self.transactions.get(transaction_id)
        if not tx:
            raise ValueError(f"Transaction {transaction_id} tidak ditemukan!")

        if tx.status not in [
            TransactionStatus.ACTIVE,
            TransactionStatus.PARTIALLY_COMMITTED,
        ]:
            print(
                f"[TxManager] Warning: TX {transaction_id} sudah dalam status {tx.status.value}"
            )
            return

        tx.status = TransactionStatus.FAILED
        print(f"[TxManager] ✗ TX {transaction_id} FAILED: {reason}")

    def abort_transaction(self, transaction_id: int):
        tx = self.transactions.get(transaction_id)
        if not tx:
            raise ValueError(f"Transaction {transaction_id} tidak ditemukan!")

        if not tx.can_abort():
            raise ValueError(
                f"TX {transaction_id} tidak bisa di-abort. "
                f"Status: {tx.status.value}"
            )

        tx.status = TransactionStatus.ABORTED
        tx.abort_time = datetime.now()

        if transaction_id in self.active_transactions:
            self.active_transactions.remove(transaction_id)
        self.aborted_transactions.add(transaction_id)

        print(f"[TxManager] ⮌ TX {transaction_id} ABORTED (rolled back)")

    def terminate_transaction(self, transaction_id: int):
        tx = self.transactions.get(transaction_id)
        if not tx:
            raise ValueError(f"Transaction {transaction_id} tidak ditemukan!")

        if tx.status not in [TransactionStatus.COMMITTED, TransactionStatus.ABORTED]:
            raise ValueError(
                f"TX {transaction_id} harus COMMITTED atau ABORTED dulu. "
                f"Status: {tx.status.value}"
            )

        tx.status = TransactionStatus.TERMINATED
        print(f"[TxManager] TX {transaction_id} TERMINATED (keluar dari sistem)")

    def detect_deadlock(self) -> Optional[List[int]]:
        wait_for_graph: Dict[int, Set[int]] = {}

        for tx_id in self.active_transactions:
            tx = self.transactions[tx_id]
            if tx.waiting_for is not None:
                if tx_id not in wait_for_graph:
                    wait_for_graph[tx_id] = set()
                wait_for_graph[tx_id].add(tx.waiting_for)

        def has_cycle(
            node: int, visited: Set[int], rec_stack: Set[int], path: List[int]
        ) -> Optional[List[int]]:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            if node in wait_for_graph:
                for neighbor in wait_for_graph[node]:
                    if neighbor not in visited:
                        result = has_cycle(neighbor, visited, rec_stack, path.copy())
                        if result:
                            return result
                    elif neighbor in rec_stack:
                        cycle_start = path.index(neighbor)
                        return path[cycle_start:]

            rec_stack.remove(node)
            return None

        visited = set()
        for tx_id in wait_for_graph:
            if tx_id not in visited:
                cycle = has_cycle(tx_id, visited, set(), [])
                if cycle:
                    print(f"[TxManager] ⚠ DEADLOCK DETECTED: {cycle}")
                    return cycle

        return None

    def get_statistics(self) -> Dict[str, int]:
        return {
            "total_transactions": len(self.transactions),
            "active": len(self.active_transactions),
            "committed": len(self.committed_transactions),
            "aborted": len(self.aborted_transactions),
        }

    def __repr__(self):
        stats = self.get_statistics()
        return (
            f"TransactionManager("
            f"total={stats['total_transactions']}, "
            f"active={stats['active']}, "
            f"committed={stats['committed']}, "
            f"aborted={stats['aborted']})"
        )
