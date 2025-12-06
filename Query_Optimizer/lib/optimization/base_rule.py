from abc import ABC, abstractmethod
from typing import Optional
import logging
from globalsy.classes.query_tree import QueryTree


class OptimizationRule(ABC):

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    @abstractmethod
    def can_apply(self, tree: QueryTree) -> bool:
        raise NotImplementedError

    @abstractmethod
    def apply(self, tree: QueryTree) -> QueryTree:
        raise NotImplementedError

    def _log(self, level: str, message: str):
        if self.logger:
            log_method = getattr(self.logger, level.lower(), None)
            if log_method:
                log_method(f"[{self.__class__.__name__}] {message}")
