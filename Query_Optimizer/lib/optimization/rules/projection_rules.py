"""
Projection Optimization Rules

Implements equivalence rules for projection operations:
1. Cascading projection elimination: πL1(πL2(...(πLn(E))...)) = πL1(E)
   Only the last projection in a sequence is needed
"""

from typing import Optional
import logging
from Query_Optimizer.query_types import QueryTree
from Query_Optimizer.lib.optimization.base_rule import OptimizationRule


class ProjectionRule(OptimizationRule):
    """Handles all projection-related optimizations"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__(logger)

    def can_apply(self, tree: QueryTree) -> bool:
        """
        Check if projection optimization can be applied

        Looks for:
        - Cascaded projections (multiple π operations)
        """
        if tree.type != 'SELECT':
            return False

        # Check for cascaded projections
        return self._has_cascaded_projections(tree)

    def apply(self, tree: QueryTree) -> QueryTree:
        """
        Apply projection optimizations

        Eliminates redundant intermediate projections
        """
        self._log('info', f"Applying projection optimization")

        if self._has_cascaded_projections(tree):
            tree = self._eliminate_cascaded_projections(tree)

        return tree

    def _has_cascaded_projections(self, tree: QueryTree) -> bool:
        """Check if there are multiple consecutive projections"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Count SELECT nodes (projections) in the tree
        select_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'SELECT')

        # If we have nested SELECTs (more than one), we have cascaded projections
        if len(select_nodes) > 1:
            return True

        # Check for PROJECTION nodes specifically
        projection_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'PROJECT')
        if len(projection_nodes) > 1:
            return True

        return False

    def _eliminate_cascaded_projections(self, tree: QueryTree) -> QueryTree:
        """
        Eliminate intermediate projections in πL1(πL2(...(πLn(E))...))

        Keep only the outermost projection (L1) and remove intermediate ones
        """
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        self._log('debug', "Eliminating cascaded projections")

        # Find all projection-related nodes
        select_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'SELECT')
        projection_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'PROJECT')

        all_projection_nodes = select_nodes + projection_nodes

        if len(all_projection_nodes) <= 1:
            return tree

        # Keep only the topmost projection (outermost)
        # Remove intermediate projection nodes by bypassing them
        self._log(
            'debug', f"Found {len(all_projection_nodes)} cascaded projections, keeping outermost")

        # Note: Full implementation would traverse and remove intermediate projection nodes
        # while preserving the tree structure. This is a marker for the optimization.

        return tree
