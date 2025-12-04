import socket
import threading
import argparse
import json
from Query_Processor.classes import QueryProcessor
from Query_Optimizer.optimization_engine import OptimizationEngine
from Concurrency_Control_Manager.classes import ConcurrencyControlManager
from Storage_Manager.storage_engine import StorageEngine
from Storage_Manager.serializer import Serializer
from Failure_Recovery.buffer_manager import BufferManager
from Failure_Recovery.failure_recovery_manager import FailureRecoveryManager

HOST = 'localhost'
PORT = 8080


class Server:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        print("--- mini Database Management System (mDBMS) Server ---")
        print("Initializing DBMS components...")

        self.optimizer = OptimizationEngine()
        self.serializer = Serializer()

        self.storage = StorageEngine(serializer=self.serializer)

        buffer_manager = BufferManager(capacity=100)

        self.frm = FailureRecoveryManager(
            buffer_manager=buffer_manager,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory="logs",
            checkpoint_interval=10
        )

        self.storage.frm = self.frm
        self.cc_manager = ConcurrencyControlManager(frm=self.frm)
        self.storage.cc_manager = self.cc_manager

        self.qp = QueryProcessor(
            optimizer=self.optimizer,
            storage_manager=self.storage,
            cc_manager=self.cc_manager,
            fr_manager=self.frm
        )

        self.server_socket = None
        self.running = False
        self.client_count = 0
        self.client_lock = threading.Lock()

        self._initialized = True
        print("[Server] DBMS components initialized successfully.")

    def format_result(self, results):
        output = []
        DISPLAY_LIMIT = 10  # Maximum number of rows to display

        print(f"[Server Debug] Formatting {len(results)} results")
        for idx, result in enumerate(results):
            print(
                f"[Server Debug] Result {idx}: has_data={result.data is not None}, rows_count={result.rows_count}, message='{result.message}'")

            # Show ExecutionResult metadata
            metadata = f"[TID: {result.transaction_id}] {result.message}"

            # Check if we have data to display (for SELECT queries)
            has_data = result.data and hasattr(
                result.data, 'data') and result.data.data

            if has_data:
                rows = result.data.data
                print(
                    f"[Server Debug] Result {idx} has {len(rows)} rows of data")
                if rows:
                    output.append(f"\n{metadata}")

                    # Limit displayed rows to DISPLAY_LIMIT
                    total_rows = len(rows)
                    display_rows = rows[:DISPLAY_LIMIT]

                    columns = list(display_rows[0].keys())
                    col_widths = {col: len(col) for col in columns}

                    for row in display_rows:
                        for col in columns:
                            col_widths[col] = max(
                                col_widths[col], len(str(row[col])))

                    header = "| " + \
                        " | ".join(col.ljust(col_widths[col])
                                   for col in columns) + " |"
                    separator = "+-" + \
                        "-+-".join("-" * col_widths[col]
                                   for col in columns) + "-+"

                    output.append(separator)
                    output.append(header)
                    output.append(separator)

                    for row in display_rows:
                        output.append(
                            "| " + " | ".join(str(row[col]).ljust(col_widths[col]) for col in columns) + " |")

                    output.append(separator)

                    # Show row count with indication if limited
                    if total_rows > DISPLAY_LIMIT:
                        output.append(
                            f"Showing {DISPLAY_LIMIT} of {result.rows_count} rows")
                        output.append(
                            f"(Use LIMIT clause to control number of rows)\n")
                    else:
                        output.append(f"({result.rows_count} rows)\n")
                else:
                    # Empty result set for SELECT query
                    output.append(f"\n{metadata}")
                    output.append("(0 rows)\n")
            else:
                # Non-SELECT queries (INSERT, UPDATE, DELETE, etc.) or messages without data
                output.append(f"\n{metadata}")
                # Only show rows affected if > 0, otherwise it's just a message
                if result.rows_count > 0 and "committed successfully" not in result.message.lower():
                    output.append(f"({result.rows_count} rows affected)\n")
                else:
                    output.append("")  # Just newline for messages

        return "\n".join(output)

    def handle_client(self, client_socket, client_address):
        with self.client_lock:
            self.client_count += 1
            client_id = self.client_count

        print(f"[Server] Client {client_id} connected from {client_address}")

        try:
            welcome = f"[mDBMS Server] Connected as Client {client_id}. Type your SQL query or 'exit' to quit.\n"
            client_socket.send(welcome.encode('utf-8'))

            buffer = ""
            while True:
                try:
                    chunk = client_socket.recv(4096).decode('utf-8')
                    if not chunk:
                        break

                    buffer += chunk

                    # Process complete messages (line-delimited JSON)
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if not line.strip():
                            continue

                        try:
                            message = json.loads(line)
                            msg_id = message.get("id")
                            msg_type = message.get("type")
                            content = message.get("content", "")

                            # Handle heartbeat silently
                            if msg_type == "HEARTBEAT":
                                response_msg = json.dumps({
                                    "id": msg_id,
                                    "type": "HEARTBEAT",
                                    "content": "PONG"
                                }) + "\n"
                                client_socket.send(
                                    response_msg.encode('utf-8'))
                                continue

                            # Handle query
                            if msg_type == "QUERY":
                                print(
                                    f"[Server] Client {client_id} query: {content}")

                                if content.lower() == 'exit':
                                    response_content = "[mDBMS Server] Goodbye!\n"
                                    response_msg = json.dumps({
                                        "id": msg_id,
                                        "type": "QUERY",
                                        "content": response_content
                                    }) + "\n"
                                    client_socket.send(
                                        response_msg.encode('utf-8'))
                                    return

                                try:
                                    # Pass client address for transaction ID generation
                                    results = self.qp.execute_query(
                                        content, client_address)
                                    response_content = self.format_result(
                                        results)
                                    print(
                                        f"[Server] Response length: {len(response_content)} chars")
                                except FileNotFoundError as e:
                                    response_content = f"\nError: Table or schema not found. {e}\n"
                                    print(
                                        f"[Server] Client {client_id} file not found error: {e}")
                                except ValueError as e:
                                    response_content = f"\nError: {e}\n"
                                    print(
                                        f"[Server] Client {client_id} query error: {e}")
                                except KeyError as e:
                                    response_content = f"\nError: Invalid query syntax or missing element: {e}\n"
                                    print(
                                        f"[Server] Client {client_id} query error: {e}")
                                except AttributeError as e:
                                    response_content = f"\nError: Query parsing failed: {e}\n"
                                    print(
                                        f"[Server] Client {client_id} query error: {e}")
                                except Exception as e:
                                    response_content = f"\n[mDBMS Error] An unexpected error occurred: {e}\n"
                                    print(
                                        f"[Server] Client {client_id} unexpected error: {e}")

                                response_msg = json.dumps({
                                    "id": msg_id,
                                    "type": "QUERY",
                                    "content": response_content
                                }) + "\n"
                                client_socket.send(
                                    response_msg.encode('utf-8'))

                        except json.JSONDecodeError:
                            # Skip malformed messages
                            continue

                except ConnectionResetError:
                    break
                except Exception as e:
                    print(f"[Server] Error in client {client_id} loop: {e}")
                    break

        except ConnectionResetError:
            print(f"[Server] Client {client_id} connection reset")
        except Exception as e:
            print(f"[Server] Error handling client {client_id}: {e}")
        finally:
            client_socket.close()
            print(
                f"[Server] Client {client_id} disconnected from {client_address}")

    def start(self, host=HOST, port=PORT):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1.0)

        try:
            self.server_socket.bind((host, port))
            self.server_socket.listen()
            self.running = True

            print(f"[Server] Listening on {host}:{port}")
            print("[Server] Waiting for client connections...\n")

            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"[Server] Error accepting connection: {e}")

        except KeyboardInterrupt:
            print("\n[Server] Shutting down...")
        finally:
            self.running = False
            if self.server_socket:
                self.server_socket.close()
            print("[Server] Server stopped.")


def main():
    parser = argparse.ArgumentParser(
        description='mDBMS Server',
        epilog='Example: python server.py -host localhost -port 8080'
    )
    parser.add_argument('-host', type=str, required=True, help='Host address')
    parser.add_argument('-port', type=int, required=True, help='Port number')
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')

    server = Server()
    try:
        server.start(host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\n[Server] Server interrupted by user")
    except Exception as e:
        print(f"[Server] Fatal error: {e}")


if __name__ == "__main__":
    main()
