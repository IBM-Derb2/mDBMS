"""
Base class for optimization rules
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging
from Query_Optimizer.types import QueryTree


class OptimizationRule(ABC):
    """Abstract base class for all optimization rules"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    @abstractmethod
    def can_apply(self, tree: QueryTree) -> bool:
        """
        Check if this rule can be applied to the given query tree

        Args:
            tree: The query tree to check

        Returns:
            True if the rule can be applied, False otherwise
        """
        pass

    @abstractmethod
    def apply(self, tree: QueryTree) -> QueryTree:
        """
        Apply the optimization rule to the query tree

        Args:
            tree: The query tree to optimize

        Returns:
            The optimized query tree
        """
        pass

    def _log(self, level: str, message: str):
        """Helper method for logging"""
        if self.logger:
            log_method = getattr(self.logger, level.lower(), None)
            if log_method:
                log_method(f"[{self.__class__.__name__}] {message}")
