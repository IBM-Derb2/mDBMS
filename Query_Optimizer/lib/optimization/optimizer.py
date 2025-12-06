from typing import Optional, List
import logging
from globalsy.classes.query_tree import QueryTree
from globalsy.classes.parsed_query import ParsedQuery
from .base_rule import OptimizationRule
from .rules.selection_rules import SelectionRule
from .rules.projection_rules import ProjectionRule
from .rules.join_rules import JoinRule
from .rules.distribution_rules import DistributionRule


class QueryOptimizer:
    """
    Optimization Strategy:
    1. Push selections down (paling mengurangi row yang diproses)
    2. Push projections down (mengurangi kolom yang diproses)
    3. Optimize join order (mengurangi biaya join)
    4. Eliminate redundant operations
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

        self.rules: List[OptimizationRule] = [
            DistributionRule(logger),      # Priority 1: Push operations down
            SelectionRule(logger),         # Priority 2: Optimize selections
            ProjectionRule(logger),        # Priority 3: Eliminate redundant projections
            JoinRule(logger),              # Priority 4: Optimize join order
        ]

    def optimize(self, parsed_query: ParsedQuery) -> ParsedQuery:

        self._log(
            'info', f"Starting optimization for query type: {parsed_query.query_tree.type}")

        optimized_tree = parsed_query.query_tree
        iteration = 0
        max_iterations = 10  # prevent infinite loops

        while iteration < max_iterations:
            iteration += 1
            self._log('debug', f"Optimization iteration {iteration}")

            tree_changed = False

            for rule in self.rules:
                if rule.can_apply(optimized_tree):
                    self._log('debug', f"Applying {rule.__class__.__name__}")

                    tree_before = self._tree_to_string(optimized_tree)
                    optimized_tree = rule.apply(optimized_tree)

                    tree_after = self._tree_to_string(optimized_tree)
                    if tree_before != tree_after:
                        tree_changed = True
                        self._log(
                            'debug', f"{rule.__class__.__name__} modified the tree")

            if not tree_changed:
                self._log(
                    'info', f"Optimization converged after {iteration} iteration(s)")
                break

        if iteration >= max_iterations:
            self._log(
                'warning', f"Optimization stopped at maximum iterations ({max_iterations})")

        return ParsedQuery(
            query_tree=optimized_tree,
            query=parsed_query.query
        )

    def _tree_to_string(self, tree: QueryTree) -> str:
        return str(tree)

    def _log(self, level: str, message: str):
        if self.logger:
            log_method = getattr(self.logger, level.lower(), None)
            if log_method:
                log_method(f"[QueryOptimizer] {message}")
