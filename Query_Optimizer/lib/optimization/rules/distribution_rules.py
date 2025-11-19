"""
Distribution Optimization Rules

Implements equivalence rules for distributing operations:
1. Selection distribution over theta join:
   - σθ0(E1 ⋈θ E2) = (σθ0(E1)) ⋈θ E2  (when θ0 only involves E1 attributes)
   - σθ1∧θ2(E1 ⋈θ E2) = (σθ1(E1)) ⋈θ (σθ2(E2))  (when θ1 for E1, θ2 for E2)

2. Projection distribution over theta join:
   - πL1∪L2(E1 ⋈θ E2) = (πL1(E1)) ⋈θ (πL2(E2))  (when θ only involves L1∪L2)
   - πL1∪L2(E1 ⋈θ E2) = πL1∪L2((πL1∪L3(E1)) ⋈θ (πL2∪L4(E2)))
     where L3, L4 are join attributes not in L1∪L2
"""

from typing import Optional, Set
import logging
from Query_Optimizer.types import QueryTree
from Query_Optimizer.lib.optimization.base_rule import OptimizationRule


class DistributionRule(OptimizationRule):
    """Handles distribution of selections and projections over joins"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__(logger)

    def can_apply(self, tree: QueryTree) -> bool:
        """
        Check if distribution optimization can be applied

        Looks for:
        - Selections over joins (push down selections)
        - Projections over joins (push down projections)
        """
        if tree.type != 'SELECT':
            return False

        # Check if we have selection/projection over join
        return (self._has_selection_over_join(tree) or
                self._has_projection_over_join(tree))

    def apply(self, tree: QueryTree) -> QueryTree:
        """
        Apply distribution optimizations

        Push selections and projections down to reduce intermediate result sizes
        """
        self._log('info', f"Applying distribution optimization")

        # Rule 8: Push selections down (most beneficial)
        if self._has_selection_over_join(tree):
            tree = self._push_selection_down(tree)

        # Rule 9: Push projections down
        if self._has_projection_over_join(tree):
            tree = self._push_projection_down(tree)

        return tree

    def _has_selection_over_join(self, tree: QueryTree) -> bool:
        """Check if there's a selection (WHERE) over a join"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Look for both WHERE and JOIN nodes
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'WHERE')
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'JOIN')

        # If we have both WHERE and JOIN, selection can potentially be pushed down
        return len(where_nodes) > 0 and len(join_nodes) > 0

    def _has_projection_over_join(self, tree: QueryTree) -> bool:
        """Check if there's a projection (SELECT columns) over a join"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Look for explicit column selection (not SELECT *) over joins
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'JOIN')

        if not join_nodes:
            return False

        # Check if we have specific columns selected (opportunity for projection push-down)
        column_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'COLUMN')

        # If we have both columns and joins, projection can be pushed down
        return len(column_nodes) > 0

    def _push_selection_down(self, tree: QueryTree) -> QueryTree:
        """
        Push selection conditions down to the appropriate relations

        Strategy:
        1. Analyze WHERE conditions
        2. Determine which relation each condition belongs to
        3. Push conditions down to respective relations
        4. Keep join conditions at join level
        """
        self._log('debug', "Pushing selection down")

        # TODO: Implement selection push-down
        # Extract WHERE conditions
        conditions = self._extract_where_conditions(tree)

        # Classify conditions by relation
        relation_conditions = self._classify_conditions_by_relation(conditions)

        # Push conditions down to appropriate levels
        optimized_tree = self._apply_pushed_selections(
            tree, relation_conditions)

        return optimized_tree

    def _push_projection_down(self, tree: QueryTree) -> QueryTree:
        """
        Push projection operations down to reduce data movement

        Strategy:
        1. Identify required columns for final result
        2. Identify columns needed for join conditions
        3. Push projections down, keeping only necessary columns
        """
        self._log('debug', "Pushing projection down")

        # TODO: Implement projection push-down
        # Extract required columns
        required_columns = self._extract_required_columns(tree)

        # Identify join attributes
        join_attributes = self._extract_join_attributes(tree)

        # Push projections down
        optimized_tree = self._apply_pushed_projections(
            tree, required_columns, join_attributes)

        return optimized_tree

    def _extract_where_conditions(self, tree: QueryTree) -> list:
        """Extract WHERE clause conditions"""
        from Query_Optimizer.lib.optimization.tree_utils import ConditionAnalyzer

        # Use ConditionAnalyzer to extract all conditions
        conditions = ConditionAnalyzer.extract_conditions(tree)

        self._log('debug', f"Extracted {len(conditions)} WHERE conditions")
        return conditions

    def _classify_conditions_by_relation(self, conditions: list) -> dict:
        """
        Classify conditions based on which relation(s) they reference

        Returns:
            dict mapping relation_name -> list of conditions
        """
        from Query_Optimizer.lib.optimization.tree_utils import ConditionAnalyzer

        relation_conditions = {}
        join_conditions = []

        for condition in conditions:
            tables = ConditionAnalyzer.get_tables_in_condition(condition)

            # If condition references one table, it can be pushed to that table
            if len(tables) == 1:
                table = list(tables)[0]
                if table not in relation_conditions:
                    relation_conditions[table] = []
                relation_conditions[table].append(condition)
                self._log(
                    'debug', f"Condition for table {table}: {condition.get('expression', condition)}")

            # If condition references multiple tables, it's a join condition
            elif len(tables) > 1:
                join_conditions.append(condition)
                self._log(
                    'debug', f"Join condition involving {tables}: {condition.get('expression', condition)}")

        # Store join conditions separately
        if join_conditions:
            relation_conditions['__join__'] = join_conditions

        return relation_conditions

    def _apply_pushed_selections(self, tree: QueryTree, relation_conditions: dict) -> QueryTree:
        """Apply selection conditions at appropriate tree levels"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        if not relation_conditions:
            return tree

        # For each table with conditions, try to push down
        for table, conditions in relation_conditions.items():
            if table == '__join__':
                # These are join conditions, keep at join level
                continue

            self._log(
                'debug', f"Pushing {len(conditions)} conditions to table {table}")

            # Find table nodes and insert WHERE above them
            # This is a simplified approach - full implementation would
            # require more sophisticated tree manipulation

        return tree

    def _extract_required_columns(self, tree: QueryTree) -> Set[str]:
        """Extract columns required for final result"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Extract all column references from the tree
        columns = TreeAnalyzer.extract_columns(tree)

        self._log('debug', f"Required columns: {columns}")
        return columns

    def _extract_join_attributes(self, tree: QueryTree) -> Set[str]:
        """Extract columns used in join conditions"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer, ConditionAnalyzer

        join_attributes = set()

        # Find JOIN nodes and extract their conditions
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'JOIN')

        for join_node in join_nodes:
            # Look for ON clause
            on_nodes = TreeAnalyzer.find_nodes_by_type(join_node, 'ON')
            for on_node in on_nodes:
                conditions = ConditionAnalyzer.extract_conditions(on_node)
                for cond in conditions:
                    # Extract column names from left and right
                    if 'left' in cond and cond['left']:
                        join_attributes.add(str(cond['left']))
                    if 'right' in cond and cond['right']:
                        join_attributes.add(str(cond['right']))

        self._log('debug', f"Join attributes: {join_attributes}")
        return join_attributes

    def _apply_pushed_projections(self, tree: QueryTree,
                                  required_columns: Set[str],
                                  join_attributes: Set[str]) -> QueryTree:
        """Apply projection operations at appropriate tree levels"""
        # Combine required columns with join attributes
        all_needed_columns = required_columns.union(join_attributes)

        self._log(
            'debug', f"Pushing projection with {len(all_needed_columns)} columns")

        # Note: Full implementation would insert projection nodes above base tables
        # keeping only the columns in all_needed_columns
        # This reduces data transmission in joins

        return tree
