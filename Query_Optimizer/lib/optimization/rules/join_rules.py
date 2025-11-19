"""
Join Optimization Rules

Implements equivalence rules for join operations:
1. Join commutativity: E1 ⋈θ E2 = E2 ⋈θ E1
2. Natural join associativity: (E1 ⋈ E2) ⋈ E3 = E1 ⋈ (E2 ⋈ E3)
3. Theta join associativity: (E1 ⋈θ1 E2) ⋈θ1∧θ2 E3 = E1 ⋈θ1∧θ2 (E2 ⋈θ2 E3)
   where θ2 only involves attributes from E2 and E3
"""

from typing import Optional, List
import logging
from Query_Optimizer.types import QueryTree
from Query_Optimizer.lib.optimization.base_rule import OptimizationRule
from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer


class JoinRule(OptimizationRule):
    """Handles all join-related optimizations"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__(logger)

    def can_apply(self, tree: QueryTree) -> bool:
        """
        Check if join optimization can be applied

        Looks for:
        - Multiple joins that can be reordered
        - Join trees that can benefit from different ordering
        """
        # TODO: Implement logic to detect joins
        return self._has_multiple_joins(tree)

    def apply(self, tree: QueryTree) -> QueryTree:
        """
        Apply join optimizations

        Uses cost-based heuristics to:
        1. Reorder joins for better performance
        2. Apply associativity to create better join orders
        3. Use commutativity to swap join operands
        """
        self._log('info', f"Applying join optimization")

        if self._has_multiple_joins(tree):
            tree = self._optimize_join_order(tree)

        return tree

    def _has_multiple_joins(self, tree: QueryTree) -> bool:
        """Check if query has multiple joins"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Count JOIN nodes in the tree
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'JOIN')

        # If we have 2 or more joins, optimization is worthwhile
        return len(join_nodes) >= 2

    def _optimize_join_order(self, tree: QueryTree) -> QueryTree:
        """
        Optimize join order using cost-based heuristics

        Strategies:
        - Smallest tables first (to minimize intermediate results)
        - Most selective joins first
        - Apply associativity and commutativity
        """
        # TODO: Implement join ordering optimization
        self._log('debug', "Optimizing join order")

        # Step 1: Extract all join operations
        joins = self._extract_joins(tree)

        # Step 2: Calculate cost for different orderings
        best_order = self._find_best_join_order(joins, tree)

        # Step 3: Reconstruct tree with optimal order
        optimized_tree = self._reconstruct_join_tree(tree, best_order)

        return optimized_tree

    def _extract_joins(self, tree: QueryTree) -> List[QueryTree]:
        """Extract all join operations from the tree"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Find all JOIN nodes
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'JOIN')

        self._log('debug', f"Extracted {len(join_nodes)} join operations")
        return join_nodes

    def _find_best_join_order(self, joins: List[QueryTree], tree: QueryTree) -> List[QueryTree]:
        """
        Find the best join order using heuristics or cost calculation

        Heuristics:
        1. Start with smallest relations
        2. Prioritize joins with selection conditions
        3. Consider intermediate result sizes
        """
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer
        if len(joins) <= 1:
            return joins

        self._log('debug', f"Optimizing order of {len(joins)} joins")

        # Heuristic: Sort joins by estimated selectivity
        # Joins with more selective conditions should be executed first
        # This is a simplified approach - full implementation would use statistics
        # Table row count
        tables = []
        tables.extend(TreeAnalyzer.extract_tables(tree))
        
        conditions = []
        for join in joins:
            conditions.append(self._extract_join_conditions(join))

        selectivity_analysis = self._analyze_joins_selectivity(conditions)
        ordered_join = []
        for sel in selectivity_analysis:
            for join in joins:
                if sel['condition'] == self._extract_join_conditions(join):
                    ordered_join.append(join)
                    break
        # For now, keep original order but log the optimization opportunity
        # self._log('debug', "Join reordering opportunity identified")

        return ordered_join

    def _analyze_joins_selectivity(self, condition: List[dict]) -> List[dict]:
        """Analyze selectivity of a join based on conditions and table stats"""
        analyzed = []
        for cond in condition:
            left_col = cond['left'].split('.')[1]
            right_col = cond['right'].split('.')[1]
            selectivity = self._estimate_join_selectivity(
                cond['left_table'], cond['right_table'], left_col, right_col, cond['operator'])
            analyzed.append({
                'condition': cond,
                'selectivity': selectivity
            })
        analyzed.sort(key=lambda x: x['selectivity'])
        return analyzed

    def _estimate_join_selectivity(self, left_table: str, right_table: str, left_col, right_col, operator) -> float:
        """Estimate selectivity of a join condition"""
        from Query_Optimizer.lib.cost.statistics import get_statistics_manager
        stats_mgr = get_statistics_manager()
        # Fetch statistics
        left_stats = stats_mgr.get_table_stats(left_table)
        right_stats = stats_mgr.get_table_stats(right_table)
        # Simplified selectivity estimation
        if operator == '=':
            max_distinct = max(left_stats.column_stats[left_col]["distinct_values"],
                               right_stats.column_stats[right_col]["distinct_values"])
            selectivity = 1.0 / max_distinct if max_distinct > 0 else 1.0
        elif operator in ('<', '>', '<=', '>='):
            selectivity = 0.33 # Rough estimate for range joins
        elif operator == '!=':
            max_distinct = max(left_stats.column_stats[left_col]["distinct_values"],
                               right_stats.column_stats[right_col]["distinct_values"])
            selectivity = 1-(1.0 / max_distinct) if max_distinct > 0 else 0
        return selectivity

    def _extract_join_conditions(self, join:QueryTree) -> List[dict]:
        """Extract join conditions from a join node"""
        conditions = []
        for child in join.childs:
            if child.type == 'OPERATOR':
                left_table = child.childs[0].val.split('.')[0]
                right_table = child.childs[1].val.split('.')[0]
                left = child.childs[0].val
                right = child.childs[1].val
                operator = child.val
                conditions.append({
                    'left_table': left_table,
                    'right_table': right_table,
                    'left': left,
                    'right': right,
                    'operator': operator
                })
        return conditions
    
    def _reconstruct_join_tree(self, original_tree: QueryTree, ordered_joins: List[QueryTree]) -> QueryTree:
        """Reconstruct the query tree with optimized join order"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeManipulator, TreeAnalyzer
        # TODO: Implement tree reconstruction
        self._log('debug', "Reconstructing join tree with optimized order")
        from_node = TreeAnalyzer.find_nodes_by_type(original_tree, 'FROM')[0]
        for join in ordered_joins:
            join.parent = from_node
        from_node.childs = ordered_joins
        first_table_name = ordered_joins[0].childs[1].childs[0].val.split('.')[0]
        first_table_node = QueryTree(type='TABLE', val=first_table_name, parent=from_node)
        from_node.childs.insert(0, first_table_node)
        return original_tree

    def _can_apply_commutativity(self, join: QueryTree) -> bool:
        """Check if commutativity can improve performance"""
        # Commutativity can help if:
        # 1. One relation is significantly smaller than the other
        # 2. One relation has more selective conditions

        # Check if join has two children (left and right relations)
        if len(join.childs) >= 2:
            # In practice, would compare table sizes and selectivity
            # For now, return True to indicate potential optimization
            return True

        return False

    def _can_apply_associativity(self, joins: List[QueryTree]) -> bool:
        """Check if associativity can be applied"""
        # Associativity can be applied when:
        # - We have 3+ relations to join
        # - Join conditions allow regrouping
        # - Regrouping would reduce intermediate result size

        if len(joins) >= 3:
            # Associativity is applicable
            self._log(
                'debug', f"Associativity can be applied to {len(joins)} joins")
            return True

        return False
