import socket
import argparse
import threading
import time
import os
import uuid
import json

HOST = 'localhost'
PORT = 8080
HEARTBEAT_INTERVAL = 3  # seconds
HEARTBEAT_TIMEOUT = 7  # seconds - increased for long-running queries like COMMIT


class Client:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.socket = None
        self.heartbeat_thread = None
        self.running = False
        self.last_heartbeat = time.time()
        self.heartbeat_lock = threading.Lock()
        self.receive_buffer = ""

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            # Read welcome message (non-protocol message)
            welcome = self.socket.recv(4096).decode('utf-8')
            print(welcome, end='')
            # Set non-blocking for message protocol
            self.socket.setblocking(False)
            self.running = True
            self.last_heartbeat = time.time()
            self.start_heartbeat()
            return True
        except ConnectionRefusedError:
            print(
                f"[Client Error] Could not connect to server at {self.host}:{self.port}")
            print("[Client Error] Make sure the server is running.")
            return False
        except Exception as e:
            print(f"[Client Error] Connection failed: {e}")
            return False

    def send_message(self, msg_type, content):
        """Send a message with UUID header"""
        request_id = str(uuid.uuid4())
        message = json.dumps({
            "id": request_id,
            "type": msg_type,
            "content": content
        }) + "\n"
        try:
            self.socket.send(message.encode('utf-8'))
            return request_id
        except:
            return None

    def receive_message(self, timeout=10):
        """Receive a complete message (line-delimited JSON)"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                chunk = self.socket.recv(4096).decode('utf-8')
                if not chunk:
                    return None
                self.receive_buffer += chunk

                # Check if we have a complete message (ends with newline)
                if '\n' in self.receive_buffer:
                    line, self.receive_buffer = self.receive_buffer.split(
                        '\n', 1)
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
            except BlockingIOError:
                time.sleep(0.01)
                continue
            except:
                return None
        return None

    def send_query(self, query):
        """Send query and wait for matching response"""
        request_id = self.send_message("QUERY", query)
        if not request_id:
            return None

        # Update heartbeat before waiting for potentially long query
        with self.heartbeat_lock:
            self.last_heartbeat = time.time()

        # Wait for response with matching ID and type
        start_time = time.time()
        timeout = 10
        while time.time() - start_time < timeout:
            response_msg = self.receive_message(
                timeout=timeout - (time.time() - start_time))
            if not response_msg:
                return None

            # Update heartbeat for any valid message
            with self.heartbeat_lock:
                self.last_heartbeat = time.time()

            # Check if this is the QUERY response we're waiting for
            if response_msg.get("type") == "QUERY" and response_msg.get("id") == request_id:
                return response_msg.get("content", "")

            # Skip HEARTBEAT messages and continue waiting
            if response_msg.get("type") == "HEARTBEAT":
                continue

        # Timeout waiting for query response
        return None

    def close(self):
        self.running = False
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=1)
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            print("[Client] Connection closed.")

    def heartbeat_monitor(self):
        """Monitor server connection with periodic heartbeat checks"""
        while self.running:
            time.sleep(HEARTBEAT_INTERVAL)
            if not self.running:
                break

            with self.heartbeat_lock:
                time_since_last = time.time() - self.last_heartbeat

            if time_since_last > HEARTBEAT_TIMEOUT:
                print(
                    "\n[Client Error] Server heartbeat timeout. Server not responding.")
                print("[Client] Shutting down...")
                self.running = False
                # Force exit to break out of input() blocking
                os._exit(1)

            # Send a heartbeat ping
            try:
                request_id = self.send_message("HEARTBEAT", "PING")
                if request_id:
                    # Wait briefly for PONG response
                    response_msg = self.receive_message(timeout=2)
                    if response_msg and response_msg.get("type") == "HEARTBEAT":
                        with self.heartbeat_lock:
                            self.last_heartbeat = time.time()
            except Exception:
                # Connection error during ping
                print("\n[Client Error] Lost connection to server.")
                print("[Client] Shutting down...")
                self.running = False
                # Force exit to break out of input() blocking
                os._exit(1)

    def start_heartbeat(self):
        """Start the heartbeat monitoring thread"""
        self.heartbeat_thread = threading.Thread(
            target=self.heartbeat_monitor, daemon=True)
        self.heartbeat_thread.start()

    def run(self):
        if not self.connect():
            return

        print("\n[mDBMS Client] Ready. Type your SQL query or 'exit' to quit.\n")

        try:
            while self.running:
                try:
                    query = input("IBM-Derb2> ")
                    if not query:
                        continue

                    response = self.send_query(query)
                    if response is None:
                        print("\n[Client Error] Server disconnected.")
                        break
                    print(response)

                    if query.lower() == 'exit':
                        break
                except EOFError:
                    print("\n[Client] Exiting...")
                    break
                except KeyboardInterrupt:
                    print("\n[Client] Interrupted. Exiting...")
                    break
        finally:
            self.close()


def main():
    parser = argparse.ArgumentParser(
        description='mDBMS Client',
        epilog='Example: python client.py -host localhost -port 8080'
    )
    parser.add_argument('-host', type=str, required=True,
                        help='Server host address')
    parser.add_argument('-port', type=int, required=True,
                        help='Server port number')
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')

    print("--- mini Database Management System (mDBMS) Client ---")
    client = Client(host=args.host, port=args.port)
    client.run()


if __name__ == "__main__":
    main()
