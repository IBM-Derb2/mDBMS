"""Projection Optimization Rules"""

from typing import Optional
import logging
from globalsy.classes.query_tree import QueryTree
from globalsy.constants.query_types import QueryTypes
from ..base_rule import OptimizationRule
from ..tree_utils import TreeAnalyzer

class ProjectionRule(OptimizationRule):
    """Handles all projection-related optimizations"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__(logger)

    def can_apply(self, tree: QueryTree) -> bool:
        if tree.type != QueryTypes.PROJECTION:
            return False
        return self._has_cascaded_projections(tree)

    def apply(self, tree: QueryTree) -> QueryTree:
        self._log('info', f"Applying projection optimization")
        if self._has_cascaded_projections(tree):
            tree = self._eliminate_cascaded_projections(tree)
        return tree

    def _has_cascaded_projections(self, tree: QueryTree) -> bool:
        select_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.SELECT)

        # kalau ada lebih dari 1 nest SELECT, pasti cascaded
        if len(select_nodes) > 1:
            return True
        projection_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.PROJECTION)
        if len(projection_nodes) > 1:
            return True
        return False

    def _eliminate_cascaded_projections(self, tree: QueryTree) -> QueryTree:
        self._log('debug', "Eliminating cascaded projections")

        projection_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.PROJECTION)

        if len(projection_nodes) <= 1:
            return tree

        self._log('debug', f"Found {len(projection_nodes)} cascaded projections")

        outermost = None
        for node in projection_nodes:
            if node.parent is None or node.parent.type != QueryTypes.PROJECTION:
                outermost = node
                break

        if not outermost:
            outermost = projection_nodes[0]

        nested_projections = [n for n in projection_nodes if n != outermost]

        for proj_node in nested_projections:
            if not proj_node.parent or not proj_node.childs:
                continue

            parent = proj_node.parent
            child = proj_node.childs[0]

            if proj_node in parent.childs:
                idx = parent.childs.index(proj_node)
                parent.childs[idx] = child
                child.parent = parent

                self._log('debug', f"Eliminated intermediate projection")

        return tree
