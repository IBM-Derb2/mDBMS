from abc import ABC, abstractmethod
from typing import Any
from ..classes import Response

# ABC = Abstract Base Class
class ConcurrencyStrategy(ABC):
    """
    Interface untuk semua algoritma concurrency control.
    """

    @abstractmethod
    def log_object(self, obj: Any, transaction_id: int, action: str):
        pass

    @abstractmethod
    def validate_object(self, obj: Any, transaction_id: int, action: str) -> Response:
        pass

    @abstractmethod
    def end_transaction(self, transaction_id: int):
        pass