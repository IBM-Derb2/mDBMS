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
from globalsy.classes.query_tree import QueryTree
from Query_Optimizer.lib.optimization.base_rule import OptimizationRule
from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer, TreeManipulator
from globalsy.constants.query_types import QueryTypes


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
        if tree.type != QueryTypes.SELECT:
            return False

        # Check if we have selection/projection over join
        return (self._has_selection_over_join(tree) or
                self._has_projection_over_join(tree))

    def _link_parents(self, node: QueryTree, parent: Optional[QueryTree] = None):
        """
        Helper rekursif untuk mengisi pointer parent yang hilang.
        Ini penting agar TreeManipulator bisa bekerja.
        """
        node.parent = parent
        if node.childs:
            for child in node.childs:
                self._link_parents(child, node)

    def apply(self, tree: QueryTree) -> QueryTree:
        """
        Apply distribution optimizations

        Push selections and projections down to reduce intermediate result sizes
        """
        self._log('info', f"Applying distribution optimization")

        self._link_parents(tree)

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
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.WHERE)
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.JOIN)

        # If we have both WHERE and JOIN, selection can potentially be pushed down
        return len(where_nodes) > 0 and len(join_nodes) > 0

    def _has_projection_over_join(self, tree: QueryTree) -> bool:
        """Check if there's a projection (SELECT columns) over a join"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Look for explicit column selection (not SELECT *) over joins
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.JOIN)

        if not join_nodes:
            return False

        # Check if we have specific columns selected (opportunity for projection push-down)
        column_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.COLUMN)

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
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer, TreeManipulator

        if not relation_conditions:
            return tree

        table_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.TABLE)
        if not table_nodes:
            table_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.FROM)

        for node in table_nodes:
            target_node = node
            lookup_name = node.val

            # Handle Alias
            if node.parent and node.parent.type == QueryTypes.ALIAS:
                target_node = node.parent
                lookup_name = target_node.val

            if lookup_name in relation_conditions:
                conditions = relation_conditions[lookup_name]

                expr_parts = []
                for cond in conditions:
                    if 'expression' in cond:
                        expr_parts.append(cond['expression'])
                    elif 'left' in cond and 'operator' in cond:
                        right_val = cond.get('right', '')
                        expr_parts.append(
                            f"{cond['left']} {cond['operator']} {right_val}")

                if not expr_parts:
                    continue

                combined_expression = " AND ".join(expr_parts)

                # cek duplikasi
                curr = target_node.parent
                already_exists = False
                while curr:
                    # Berhenti jika ketemu boundary (JOIN/SELECT) agar tidak scan terlalu jauh
                    if curr.type in [QueryTypes.FROM, QueryTypes.SELECT, QueryTypes.JOIN]:
                        break
                    if curr.type == QueryTypes.WHERE and curr.val == combined_expression:
                        already_exists = True
                        break
                    curr = curr.parent

                if already_exists:
                    continue

                self._log('debug', f"Pushing conditions to {lookup_name}")

                new_where_node = QueryTree(
                    type=QueryTypes.WHERE,
                    val=combined_expression,
                    childs=[],
                    parent=None
                )
                TreeManipulator.insert_node_above(target_node, new_where_node)

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
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.JOIN)

        for join_node in join_nodes:
            # Look for ON clause
            on_nodes = TreeAnalyzer.find_nodes_by_type(join_node, QueryTypes.ON)
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
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer, TreeManipulator

        all_needed_columns = required_columns.union(join_attributes)
        if not all_needed_columns:
            return tree

        table_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.TABLE)
        if not table_nodes:
            table_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.FROM)

        for node in table_nodes:
            target_node = node
            lookup_name = node.val

            if node.parent and node.parent.type == QueryTypes.ALIAS:
                target_node = node.parent
                lookup_name = target_node.val

            table_columns = set()
            for col in all_needed_columns:
                if '.' in col:
                    t_part, c_part = col.split('.', 1)
                    if t_part == lookup_name:
                        table_columns.add(col)

            if table_columns:
                proj_val = ", ".join(sorted(list(table_columns)))

                # cek duplikasi
                curr = target_node.parent
                already_exists = False
                while curr:
                    if curr.type in [QueryTypes.FROM, QueryTypes.SELECT, QueryTypes.JOIN]:
                        break
                    if curr.type == QueryTypes.PROJECT and curr.val == proj_val:
                        already_exists = True
                        break
                    curr = curr.parent

                if already_exists:
                    continue

                self._log('debug', f"Pushing projection to {lookup_name}")

                new_project_node = QueryTree(
                    type=QueryTypes.PROJECT,
                    val=proj_val,
                    childs=[],
                    parent=None
                )
                TreeManipulator.insert_node_above(
                    target_node, new_project_node)

        return tree
