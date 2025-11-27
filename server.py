import socket
import threading
import argparse
from Query_Processor.classes import QueryProcessor
from Query_Optimizer.optimization_engine import OptimizationEngine
from Concurrency_Control_Manager.classes import ConcurrencyControlManager
from Storage_Manager.storage_engine import StorageEngine
from Failure_Recovery.classes import FailureRecovery

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
        self.storage = StorageEngine()
        self.cc_manager = ConcurrencyControlManager()
        self.fr_manager = FailureRecovery()

        self.qp = QueryProcessor(
            optimizer=self.optimizer,
            storage_manager=self.storage,
            cc_manager=self.cc_manager,
            fr_manager=self.fr_manager
        )

        self.server_socket = None
        self.running = False
        self.client_count = 0
        self.client_lock = threading.Lock()

        self._initialized = True
        print("[Server] DBMS components initialized successfully.")

    def format_result(self, results):
        output = []

        for result in results:
            if result.data and result.data.data:
                rows = result.data.data
                if rows:
                    columns = list(rows[0].keys())
                    col_widths = {col: len(col) for col in columns}

                    for row in rows:
                        for col in columns:
                            col_widths[col] = max(col_widths[col], len(str(row[col])))

                    header = "| " + " | ".join(col.ljust(col_widths[col]) for col in columns) + " |"
                    separator = "+-" + "-+-".join("-" * col_widths[col] for col in columns) + "-+"

                    output.append("\n" + separator)
                    output.append(header)
                    output.append(separator)

                    for row in rows:
                        output.append("| " + " | ".join(str(row[col]).ljust(col_widths[col]) for col in columns) + " |")

                    output.append(separator)
                    output.append(f"\n({result.rows_count} rows)\n")
            else:
                output.append(f"\n{result.message}")
                if result.rows_count > 0:
                    output.append(f"({result.rows_count} rows affected)\n")
                else:
                    output.append("")

        return "\n".join(output)

    def handle_client(self, client_socket, client_address):
        with self.client_lock:
            self.client_count += 1
            client_id = self.client_count

        print(f"[Server] Client {client_id} connected from {client_address}")

        try:
            welcome = f"[mDBMS Server] Connected as Client {client_id}. Type your SQL query or 'exit' to quit.\n"
            client_socket.send(welcome.encode('utf-8'))

            while True:
                data = client_socket.recv(4096).decode('utf-8').strip()
                if not data:
                    break

                print(f"[Server] Client {client_id} query: {data}")

                if data.lower() == 'exit':
                    goodbye = "[mDBMS Server] Goodbye!\n"
                    client_socket.send(goodbye.encode('utf-8'))
                    break

                try:
                    results = self.qp.execute_query(data)
                    response = self.format_result(results)
                except ValueError as e:
                    response = f"\nError: {e}\n"
                except Exception as e:
                    response = f"\n[mDBMS Error] An unexpected error occurred: {e}\n"

                client_socket.send(response.encode('utf-8'))

        except ConnectionResetError:
            print(f"[Server] Client {client_id} connection reset")
        except Exception as e:
            print(f"[Server] Error handling client {client_id}: {e}")
        finally:
            client_socket.close()
            print(f"[Server] Client {client_id} disconnected from {client_address}")

    def start(self, host=HOST, port=PORT):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
        epilog='Example: python server.py --host localhost --port 8080'
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
