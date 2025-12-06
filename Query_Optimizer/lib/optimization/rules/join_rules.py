"""Join Optimization Rules"""

from typing import Optional, List
import logging
from globalsy.classes.query_tree import QueryTree
from globalsy.constants.query_types import QueryTypes
from ..base_rule import OptimizationRule
from ..tree_utils import TreeAnalyzer
from Query_Optimizer.lib.cost.statistics import StatisticsManager


class JoinRule(OptimizationRule):
    """Handles all join-related optimizations"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__(logger)

    def can_apply(self, tree: QueryTree) -> bool:
        return self._has_multiple_joins(tree)

    def apply(self, tree: QueryTree) -> QueryTree:
        self._log('info', f"Applying join optimization")
        if self._has_multiple_joins(tree):
            tree = self._optimize_join_order(tree)
        return tree

    def _has_multiple_joins(self, tree: QueryTree) -> bool:
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.JOIN)

        # kalau ada 2 atau lebih JOIN, berarti bisa dioptimasi
        return len(join_nodes) >= 2

    def _optimize_join_order(self, tree: QueryTree) -> QueryTree:
        self._log('debug', "Optimizing join order with dynamic programming")
        relations = self._extract_relations_from_tree(tree)
        if len(relations) <= 2:
            return tree
        optimized_tree = self._heuristic_join_optimization(tree, relations)
        return optimized_tree

    def _extract_relations_from_tree(self, tree: QueryTree) -> List[QueryTree]:
        table_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.TABLE)

        self._log('debug', f"Extracted {len(table_nodes)} relations")
        return table_nodes

    def _heuristic_join_optimization(self, tree: QueryTree, relations: List[QueryTree]) -> QueryTree:
        stats_mgr = StatisticsManager()
        table_sizes = []
        for rel in relations:
            table_name = rel.val if rel.val else 'unknown'
            row_count = stats_mgr.get_row_count(table_name)
            table_sizes.append((row_count, table_name, rel))

        table_sizes.sort(key=lambda x: x[0])

        self._log('debug', f"Join order by table size: {[name for _, name, _ in table_sizes]}")

        join_nodes = []
        theta_joins = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.THETA_JOIN)
        natural_joins = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.NATURAL_JOIN)
        cross_joins = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.CROSS_JOIN)
        join_nodes = theta_joins + natural_joins + cross_joins

        if len(join_nodes) < 2:
            return tree

        relation_map = {rel.val: rel for _, _, rel in table_sizes}

        smallest_table = table_sizes[0][2]

        for join_node in join_nodes:
            if not join_node.childs or len(join_node.childs) < 2:
                continue

            left_child = join_node.childs[0]
            right_child = join_node.childs[1]

            left_is_relation = left_child.type == QueryTypes.RELATION
            right_is_relation = right_child.type == QueryTypes.RELATION

            if left_is_relation and right_is_relation:
                left_name = left_child.val
                right_name = right_child.val

                left_size = stats_mgr.get_row_count(left_name)
                right_size = stats_mgr.get_row_count(right_name)

                if left_size > right_size:
                    join_node.childs[0] = right_child
                    join_node.childs[1] = left_child
                    self._log('debug', f"Swapped join operands: {right_name} ⋈ {left_name}")

        return tree
