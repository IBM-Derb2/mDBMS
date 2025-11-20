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
from Query_Optimizer.query_types import QueryTree
from Query_Optimizer.lib.optimization.base_rule import OptimizationRule


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
        Optimize join order using dynamic programming (findbestplan algorithm)

        Algorithm from Database System Concepts:
        procedure findbestplan(S)
          if (bestplan[S].cost ≠ ∞)
            return bestplan[S]
          if (S contains only 1 relation)
            set bestplan[S].plan and bestplan[S].cost based on the best way
            of accessing S
          else for each non-empty subset S1 of S such that S1 ≠ S
            P1 = findbestplan(S1)
            P2 = findbestplan(S - S1)
            A = best algorithm for joining results of P1 and P2
            cost = P1.cost + P2.cost + cost of A
            if (cost < bestplan[S].cost)
              bestplan[S].cost = cost
              bestplan[S].plan = "execute P1.plan; execute P2.plan; join results of P1 and P2 using A"
          return bestplan[S]
        """
        self._log('debug', "Optimizing join order with dynamic programming")

        # Step 1: Extract all relations (tables) from joins
        relations = self._extract_relations_from_tree(tree)

        if len(relations) <= 2:
            # No optimization needed for single join
            return tree

        # Step 2: Use findbestplan algorithm
        from Query_Optimizer.lib.cost.cost_calculator import calculate_node_cost

        # For now, use a simplified heuristic approach for better performance
        # Full dynamic programming is exponential: O(3^n)
        # Heuristic: Order by table size (smallest first)
        optimized_tree = self._heuristic_join_optimization(tree, relations)

        return optimized_tree

    def _extract_joins(self, tree: QueryTree) -> List[QueryTree]:
        """Extract all join operations from the tree"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Find all JOIN nodes
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'JOIN')

        self._log('debug', f"Extracted {len(join_nodes)} join operations")
        return join_nodes

    def _extract_relations_from_tree(self, tree: QueryTree) -> List[QueryTree]:
        """Extract all table/relation nodes from the tree"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Find all TABLE nodes
        table_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'TABLE')

        self._log('debug', f"Extracted {len(table_nodes)} relations")
        return table_nodes

    def _find_best_join_order(self, joins: List[QueryTree]) -> List[QueryTree]:
        """
        Find the best join order using heuristics

        Heuristics from Database System Concepts:
        1. Perform most restrictive selection and join operations first
        2. Start with smallest relations to minimize intermediate results
        3. Prioritize joins with selection conditions
        """
        if len(joins) <= 1:
            return joins

        self._log('debug', f"Optimizing order of {len(joins)} joins")

        # Heuristic: Sort joins by estimated result size
        # Joins producing smaller results should be executed first
        from Query_Optimizer.lib.cost.cost_calculator import calculate_node_cost

        # Calculate cost for each join
        join_costs = []
        for join in joins:
            cost = calculate_node_cost(join)
            join_costs.append((cost, join))

        # Sort by cost (ascending) - cheaper joins first
        join_costs.sort(key=lambda x: x[0])

        optimized_joins = [join for cost, join in join_costs]

        self._log('debug', f"Reordered {len(optimized_joins)} joins by cost")
        return optimized_joins

    def _heuristic_join_optimization(self, tree: QueryTree, relations: List[QueryTree]) -> QueryTree:
        """
        Heuristic join optimization strategy:
        1. Perform selections early (pushed down)
        2. Start with smallest tables
        3. Join tables with smallest intermediate results

        This follows the heuristic optimization approach from the slides
        """
        from Query_Optimizer.lib.cost.statistics import get_statistics_manager

        stats_mgr = get_statistics_manager()

        # Get table sizes
        table_sizes = []
        for rel in relations:
            table_name = rel.val if rel.val else 'unknown'
            row_count = stats_mgr.get_row_count(table_name)
            table_sizes.append((row_count, table_name, rel))

        # Sort by size (ascending) - smallest first
        table_sizes.sort(key=lambda x: x[0])

        self._log(
            'debug', f"Join order by table size: {[name for _, name, _ in table_sizes]}")

        # For now, return original tree
        # Full implementation would reconstruct tree with optimal order
        return tree

    def _reconstruct_join_tree(self, original_tree: QueryTree, ordered_joins: List[QueryTree]) -> QueryTree:
        """Reconstruct the query tree with optimized join order"""
        # TODO: Implement tree reconstruction
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
