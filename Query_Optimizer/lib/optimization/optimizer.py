"""
Main Query Optimizer
Orchestrates the application of all optimization rules
"""

from typing import Optional, List
import logging
from Query_Optimizer.types import ParsedQuery, QueryTree
from Query_Optimizer.lib.optimization.base_rule import OptimizationRule
from Query_Optimizer.lib.optimization.rules import (
    SelectionRule,
    ProjectionRule,
    JoinRule,
    DistributionRule
)


class QueryOptimizer:
    """
    Main optimizer that applies optimization rules in optimal order

    Optimization Strategy:
    1. Push selections down (most beneficial - reduces data early)
    2. Push projections down (reduces columns transmitted)
    3. Optimize join order (reduces intermediate result sizes)
    4. Eliminate redundant operations
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

        # Initialize all optimization rules
        self.rules: List[OptimizationRule] = [
            DistributionRule(logger),      # Priority 1: Push operations down
            SelectionRule(logger),         # Priority 2: Optimize selections
            # Priority 3: Eliminate redundant projections
            ProjectionRule(logger),
            JoinRule(logger),              # Priority 4: Optimize join order
        ]

    def optimize(self, parsed_query: ParsedQuery) -> ParsedQuery:
        """
        Optimize the parsed query by applying all applicable rules

        Args:
            parsed_query: The parsed query to optimize

        Returns:
            Optimized ParsedQuery with modified query tree
        """
        self._log(
            'info', f"Starting optimization for query type: {parsed_query.query_tree.type}")

        # Make a copy of the query tree for optimization
        optimized_tree = parsed_query.query_tree

        # Apply optimization rules iteratively
        iteration = 0
        max_iterations = 10  # Prevent infinite loops

        while iteration < max_iterations:
            iteration += 1
            self._log('debug', f"Optimization iteration {iteration}")

            # Track if any rule made changes
            tree_changed = False

            # Apply each rule in priority order
            for rule in self.rules:
                if rule.can_apply(optimized_tree):
                    self._log('debug', f"Applying {rule.__class__.__name__}")

                    # Store tree before optimization
                    tree_before = self._tree_to_string(optimized_tree)

                    # Apply the rule
                    optimized_tree = rule.apply(optimized_tree)

                    # Check if tree changed
                    tree_after = self._tree_to_string(optimized_tree)
                    if tree_before != tree_after:
                        tree_changed = True
                        self._log(
                            'debug', f"{rule.__class__.__name__} modified the tree")

            # If no rule made changes, we're done
            if not tree_changed:
                self._log(
                    'info', f"Optimization converged after {iteration} iteration(s)")
                break

        if iteration >= max_iterations:
            self._log(
                'warning', f"Optimization stopped at maximum iterations ({max_iterations})")

        # Return optimized query
        return ParsedQuery(
            query_tree=optimized_tree,
            query=parsed_query.query
        )

    def _tree_to_string(self, tree: QueryTree) -> str:
        """Convert tree to string for comparison"""
        return str(tree)

    def _log(self, level: str, message: str):
        """Helper method for logging"""
        if self.logger:
            log_method = getattr(self.logger, level.lower(), None)
            if log_method:
                log_method(f"[QueryOptimizer] {message}")
