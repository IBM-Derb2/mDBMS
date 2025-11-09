from dataclasses import dataclass
from typing import Any, Union

@dataclass
class Action:
    action: Union['write', 'read']

@dataclass
class Response:
    allowed: bool
    transaction_id: int

class ConcurrencyControlManager:
    def __init__(self):
        self._next_tid = 1

    def begin_transaction(self) -> int:
        print("[CCM Mock] Beginning new transaction.")
        tid = self._next_tid
        self._next_tid += 1
        return tid

    def log_object(self, obj: Any, transaction_id: int):
        print(f"[CCM Mock] Logging/locking object '{obj}' for TID: {transaction_id}")
        
    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        print(f"[CCM Mock] Validating action '{action}' on '{obj}' for TID: {transaction_id}")
        return Response(allowed=True, transaction_id=transaction_id)

    def end_transaction(self, transaction_id: int):
        print(f"[CCM Mock] Committing/Aborting and flushing objects for TID: {transaction_id}")
