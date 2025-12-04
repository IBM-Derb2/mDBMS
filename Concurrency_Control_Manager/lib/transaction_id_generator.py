import threading
import time


class TransactionIdGenerator:

    def __init__(self):
        self._lock = threading.Lock()
        self._counter = 0  # Counter for same timestamp collisions

    def generate(self, client_ip: str = None, client_port: int = None) -> str:
        with self._lock:
            # Get timestamp in microseconds
            timestamp = int(time.time() * 1000000)

            # Use provided client IP or default to localhost
            ip = client_ip if client_ip else "127.0.0.1"
            port = client_port if client_port else 0

            # Clean up IP (remove IPv6 wrapper if present)
            if ip.startswith("::ffff:"):
                ip = ip[7:]  # Remove ::ffff: prefix

            # Create transaction ID: IP:PORT-TIMESTAMP-COUNTER
            # Counter handles multiple transactions from same client in same microsecond
            tid = f"{ip}:{port}-{timestamp}-{self._counter}"
            # Reset counter periodically
            self._counter = (self._counter + 1) % 1000

            return tid
