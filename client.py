import socket
import argparse

HOST = 'localhost'
PORT = 8080

class Client:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.socket = None

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            welcome = self.socket.recv(4096).decode('utf-8')
            print(welcome, end='')
            return True
        except ConnectionRefusedError:
            print(f"[Client Error] Could not connect to server at {self.host}:{self.port}")
            print("[Client Error] Make sure the server is running.")
            return False
        except Exception as e:
            print(f"[Client Error] Connection failed: {e}")
            return False

    def send_query(self, query):
        try:
            self.socket.send(query.encode('utf-8'))
            response = self.socket.recv(8192).decode('utf-8')
            if not response:
                return None
            return response
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return None
        except Exception as e:
            return f"[Client Error] Failed to send query: {e}"

    def close(self):
        if self.socket:
            self.socket.close()
            print("[Client] Connection closed.")

    def run(self):
        if not self.connect():
            return

        print("\n[mDBMS Client] Ready. Type your SQL query or 'exit' to quit.\n")

        try:
            while True:
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
    parser.add_argument('-host', type=str, required=True, help='Server host address')
    parser.add_argument('-port', type=int, required=True, help='Server port number')
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')

    print("--- mini Database Management System (mDBMS) Client ---")
    client = Client(host=args.host, port=args.port)
    client.run()

if __name__ == "__main__":
    main()
