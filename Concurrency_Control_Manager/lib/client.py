import threading
import time
from typing import Callable, Optional, Any, List
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ClientOperation:
    """Represents a single operation to be performed by a client."""
    operation_type: str  # "read", "write", "commit", "abort", "sleep"
    object_id: Optional[str] = None
    value: Optional[Any] = None
    sleep_duration: float = 0.0

    def __repr__(self):
        if self.operation_type == "sleep":
            return f"{self.operation_type.upper()}({self.sleep_duration}s)"
        elif self.object_id:
            return f"{self.operation_type.upper()}({self.object_id})"
        else:
            return self.operation_type.upper()


@dataclass
class ClientExecutionLog:
    """Log entry for a client operation execution."""
    timestamp: datetime
    operation: ClientOperation
    success: bool
    error_message: Optional[str] = None
    transaction_id: Optional[int] = None

    def __repr__(self):
        status = "[OK]" if self.success else "[FAIL]"
        time_str = self.timestamp.strftime("%H:%M:%S.%f")[:-3]
        if self.error_message:
            return f"[{time_str}] {status} {self.operation} - ERROR: {self.error_message}"
        else:
            return f"[{time_str}] {status} {self.operation}"


class Client:
    """
    Represents a database client that can execute transactions.

    Each client can run operations sequentially or concurrently,
    simulating real-world database client behavior.
    """

    _client_counter = 0
    _client_lock = threading.Lock()

    def __init__(self, ccm, client_name: Optional[str] = None):
        """
        Initialize a client.

        Args:
            ccm: Reference to ConcurrencyControlManager
            client_name: Optional name for the client
        """
        with Client._client_lock:
            Client._client_counter += 1
            self.client_id = Client._client_counter

        self.client_name = client_name or f"Client-{self.client_id}"
        self.ccm = ccm
        self.current_transaction_id: Optional[int] = None
        self.execution_log: List[ClientExecutionLog] = []
        self.verbose = True

    def begin_transaction(self) -> int:
        """Start a new transaction."""
        if self.current_transaction_id is not None:
            raise Exception(f"{self.client_name} already has an active transaction {self.current_transaction_id}")

        self.current_transaction_id = self.ccm.begin_transaction()

        self._log_operation(
            ClientOperation(operation_type="begin"),
            success=True,
            transaction_id=self.current_transaction_id
        )

        if self.verbose:
            print(f"[{self.client_name}] Started TX {self.current_transaction_id}")

        return self.current_transaction_id

    def read(self, object_id: str):
        """Perform a read operation."""
        self._ensure_active_transaction()

        operation = ClientOperation(operation_type="read", object_id=object_id)

        try:
            self.ccm.log_object(object_id, self.current_transaction_id, "read")
            self._log_operation(operation, success=True, transaction_id=self.current_transaction_id)

            if self.verbose:
                print(f"[{self.client_name}] TX {self.current_transaction_id} READ '{object_id}' - SUCCESS")

        except Exception as e:
            self._log_operation(operation, success=False, error_message=str(e), transaction_id=self.current_transaction_id)

            if self.verbose:
                print(f"[{self.client_name}] TX {self.current_transaction_id} READ '{object_id}' - FAILED: {e}")

            raise

    def write(self, object_id: str, value: Any = None):
        """Perform a write operation."""
        self._ensure_active_transaction()

        operation = ClientOperation(operation_type="write", object_id=object_id, value=value)

        try:
            self.ccm.log_object(object_id, self.current_transaction_id, "write")
            self._log_operation(operation, success=True, transaction_id=self.current_transaction_id)

            if self.verbose:
                print(f"[{self.client_name}] TX {self.current_transaction_id} WRITE '{object_id}' - SUCCESS")

        except Exception as e:
            self._log_operation(operation, success=False, error_message=str(e), transaction_id=self.current_transaction_id)

            if self.verbose:
                print(f"[{self.client_name}] TX {self.current_transaction_id} WRITE '{object_id}' - FAILED: {e}")

            raise

    def commit(self):
        """Commit the current transaction."""
        self._ensure_active_transaction()

        operation = ClientOperation(operation_type="commit")
        tx_id = self.current_transaction_id

        try:
            self.ccm.commit_transaction(tx_id)
            self._log_operation(operation, success=True, transaction_id=tx_id)

            if self.verbose:
                print(f"[{self.client_name}] TX {tx_id} COMMITTED")

            self.current_transaction_id = None

        except Exception as e:
            self._log_operation(operation, success=False, error_message=str(e), transaction_id=tx_id)

            if self.verbose:
                print(f"[{self.client_name}] TX {tx_id} COMMIT FAILED: {e}")

            # Transaction failed, clear it
            self.current_transaction_id = None
            raise

    def abort(self, reason: str = "Client requested"):
        """Abort the current transaction."""
        self._ensure_active_transaction()

        operation = ClientOperation(operation_type="abort")
        tx_id = self.current_transaction_id

        try:
            self.ccm.abort_transaction(tx_id, reason)
            self._log_operation(operation, success=True, transaction_id=tx_id)

            if self.verbose:
                print(f"[{self.client_name}] TX {tx_id} ABORTED")

            self.current_transaction_id = None

        except Exception as e:
            self._log_operation(operation, success=False, error_message=str(e), transaction_id=tx_id)

            if self.verbose:
                print(f"[{self.client_name}] TX {tx_id} ABORT FAILED: {e}")

            self.current_transaction_id = None
            raise

    def sleep(self, duration: float):
        """Sleep for a specified duration (for simulating delays)."""
        operation = ClientOperation(operation_type="sleep", sleep_duration=duration)
        time.sleep(duration)
        self._log_operation(operation, success=True, transaction_id=self.current_transaction_id)

    def execute_script(self, operations: List[ClientOperation], auto_commit: bool = True):
        """
        Execute a script of operations sequentially.

        Args:
            operations: List of operations to execute
            auto_commit: Whether to automatically commit at the end
        """
        if self.verbose:
            print(f"\n[{self.client_name}] Executing script with {len(operations)} operations...")

        # Start transaction if not already started
        if self.current_transaction_id is None:
            self.begin_transaction()

        for operation in operations:
            try:
                if operation.operation_type == "read":
                    self.read(operation.object_id)
                elif operation.operation_type == "write":
                    self.write(operation.object_id, operation.value)
                elif operation.operation_type == "commit":
                    self.commit()
                    return  # Transaction ended
                elif operation.operation_type == "abort":
                    self.abort()
                    return  # Transaction ended
                elif operation.operation_type == "sleep":
                    self.sleep(operation.sleep_duration)
                else:
                    raise ValueError(f"Unknown operation type: {operation.operation_type}")

            except Exception as e:
                if self.verbose:
                    print(f"[{self.client_name}] Script execution failed: {e}")
                # Auto-abort on failure
                if self.current_transaction_id is not None:
                    try:
                        self.abort(reason=f"Script failed: {e}")
                    except:
                        pass
                raise

        # Auto-commit if requested
        if auto_commit and self.current_transaction_id is not None:
            self.commit()

    def _ensure_active_transaction(self):
        """Ensure there's an active transaction."""
        if self.current_transaction_id is None:
            raise Exception(f"{self.client_name} has no active transaction. Call begin_transaction() first.")

    def _log_operation(self, operation: ClientOperation, success: bool, error_message: Optional[str] = None, transaction_id: Optional[int] = None):
        """Log an operation to the execution log."""
        log_entry = ClientExecutionLog(
            timestamp=datetime.now(),
            operation=operation,
            success=success,
            error_message=error_message,
            transaction_id=transaction_id
        )
        self.execution_log.append(log_entry)

    def print_execution_log(self):
        """Print the execution log."""
        print(f"\n{'='*70}")
        print(f"EXECUTION LOG: {self.client_name}")
        print(f"{'='*70}")

        if not self.execution_log:
            print("(no operations)")
        else:
            for entry in self.execution_log:
                print(entry)

        print(f"{'='*70}\n")

    def get_statistics(self):
        """Get client execution statistics."""
        total_ops = len(self.execution_log)
        successful_ops = sum(1 for entry in self.execution_log if entry.success)
        failed_ops = total_ops - successful_ops

        return {
            'client_name': self.client_name,
            'total_operations': total_ops,
            'successful_operations': successful_ops,
            'failed_operations': failed_ops,
            'success_rate': (successful_ops / total_ops * 100) if total_ops > 0 else 0
        }


def run_concurrent_clients(clients: List[Client], scripts: List[List[ClientOperation]]):
    """
    Run multiple clients concurrently with their respective scripts.

    Args:
        clients: List of Client instances
        scripts: List of operation scripts (one per client)
    """
    if len(clients) != len(scripts):
        raise ValueError("Number of clients must match number of scripts")

    threads = []

    def client_worker(client: Client, script: List[ClientOperation]):
        try:
            client.execute_script(script, auto_commit=True)
        except Exception as e:
            print(f"[{client.client_name}] Thread terminated with error: {e}")

    # Start all client threads
    for client, script in zip(clients, scripts):
        thread = threading.Thread(target=client_worker, args=(client, script))
        thread.start()
        threads.append(thread)

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    print("\n" + "="*70)
    print("ALL CLIENTS COMPLETED")
    print("="*70)

    # Print statistics for each client
    for client in clients:
        stats = client.get_statistics()
        print(f"{stats['client_name']}: "
              f"{stats['successful_operations']}/{stats['total_operations']} operations successful "
              f"({stats['success_rate']:.1f}%)")
