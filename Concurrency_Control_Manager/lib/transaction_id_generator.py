import threading


class TransactionIdGenerator:

    def __init__(self):
        self._next_tid = 1
        self._lock = threading.Lock()

    def generate(self) -> int:
        with self._lock:
            tid = self._next_tid
            self._next_tid += 1
            return tid
