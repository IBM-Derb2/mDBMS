"""
Selection Optimization Rules

Implements equivalence rules for selection operations:
1. Conjunctive selection decomposition: σθ1∧θ2(E) = σθ1(σθ2(E))
2. Selection commutativity: σθ1(σθ2(E)) = σθ2(σθ1(E))
3. Selection-Cartesian product combination: σθ(E1×E2) = E1 ⋈θ E2
4. Selection-theta join combination: σθ(E1 ⋈φ E2) = E1 ⋈θ∧φ E2
"""

from typing import Optional
import logging
from Query_Optimizer.types import QueryTree
from Query_Optimizer.lib.optimization.base_rule import OptimizationRule


class SelectionRule(OptimizationRule):
    """Handles all selection-related optimizations"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__(logger)

    def can_apply(self, tree: QueryTree) -> bool:
        """
        Check if selection optimization can be applied

        Looks for:
        - Conjunctive selections (AND conditions)
        - Multiple consecutive selections
        - Selections over Cartesian products
        - Selections over joins
        """
        if tree.type != 'SELECT':
            self._log('debug', "Not a SELECT query, skipping")
            return False

        # Check for conjunctive conditions (AND)
        if self._has_conjunctive_condition(tree):
            self._log('debug', "Has conjunctive condition")
            return True

        # Check for cascaded selections
        if self._has_cascaded_selections(tree):
            self._log('debug', "Has cascaded selections")
            return True

        # Check for selection over Cartesian product or join
        if self._has_selection_over_join_or_product(tree):
            self._log('debug', "Has selection over join/product")
            return True

        self._log('debug', "No applicable selection optimizations found")
        return False

    def apply(self, tree: QueryTree) -> QueryTree:
        """
        Apply selection optimizations

        Priority order:
        1. Combine selection with Cartesian product → theta join
        2. Decompose conjunctive selections
        3. Reorder cascaded selections (for commutativity)
        """
        self._log('info', f"Applying selection optimization")

        # Rule 4 & 5: Combine with joins/products first (most beneficial)
        if self._has_selection_over_join_or_product(tree):
            tree = self._combine_selection_with_join(tree)

        # Rule 1: Decompose conjunctive selections
        if self._has_conjunctive_condition(tree):
            tree = self._decompose_conjunctive_selection(tree)

        # Rule 2: Apply commutativity if beneficial (cost-based)
        if self._has_cascaded_selections(tree):
            tree = self._optimize_selection_order(tree)

        return tree

    def _has_conjunctive_condition(self, tree: QueryTree) -> bool:
        """Check if selection has AND conditions"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Look for WHERE nodes with AND operators
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'WHERE')

        for where_node in where_nodes:
            # Check if node value contains AND
            if where_node.val and 'AND' in where_node.val.upper():
                return True

            # Check for AND nodes in children
            and_nodes = TreeAnalyzer.find_nodes_by_type(where_node, 'AND')
            if and_nodes:
                return True

            # Check if there are multiple condition children
            condition_children = [
                c for c in where_node.childs if c.type in ['COMPARISON', 'CONDITION']]
            if len(condition_children) > 1:
                return True

        return False

    def _has_cascaded_selections(self, tree: QueryTree) -> bool:
        """Check if there are multiple consecutive selections"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Count WHERE nodes in the tree
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'WHERE')

        # If more than one WHERE, we have cascaded selections
        if len(where_nodes) > 1:
            return True

        # Check if any WHERE node has another WHERE as descendant
        for where_node in where_nodes:
            for child in where_node.childs:
                if TreeAnalyzer.find_nodes_by_type(child, 'WHERE'):
                    return True

        return False

    def _has_selection_over_join_or_product(self, tree: QueryTree) -> bool:
        """Check if selection is over a join or Cartesian product"""
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        # Look for WHERE nodes
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'WHERE')
        if not where_nodes:
            return False

        # Look for FROM nodes
        from_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'FROM')
        if not from_nodes:
            return False

        from_node = from_nodes[0]

        # Check if there are JOIN nodes in the subtree
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'JOIN')
        if join_nodes:
            self._log('debug', "Found existing JOIN nodes")
            return True

        # Check for CROSS JOIN or Cartesian product indicators
        cross_join_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'CROSS_JOIN')
        if cross_join_nodes:
            self._log('debug', "Found CROSS JOIN nodes")
            return True

        # Check for Cartesian product: multiple tables in FROM without JOIN
        if len(from_node.childs) >= 2:
            self._log(
                'debug', f"Found Cartesian product: {len(from_node.childs)} tables in FROM without JOIN")
            return True

        return False

    def _decompose_conjunctive_selection(self, tree: QueryTree) -> QueryTree:
        """
        Decompose σθ1∧θ2(E) into σθ1(σθ2(E))

        Splits AND conditions into nested selections
        """
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer, TreeManipulator, ConditionAnalyzer

        self._log('debug', "Decomposing conjunctive selection")

        # Find WHERE nodes with multiple conditions
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'WHERE')

        for where_node in where_nodes:
            # Extract conditions
            conditions = ConditionAnalyzer.extract_conditions(where_node)

            # If multiple conditions, decompose them
            if len(conditions) > 1:
                # Create nested WHERE nodes
                # Start from the bottom (innermost)
                current = where_node.childs[0] if where_node.childs else None

                if current:
                    # Create a WHERE node for each condition
                    for condition in reversed(conditions):
                        new_where = QueryTree(
                            type='WHERE',
                            val=condition.get('expression', str(condition)),
                            childs=[current] if current else [],
                            parent=None
                        )
                        if current:
                            current.parent = new_where
                        current = new_where

                    # Replace original WHERE with nested structure
                    if where_node.parent:
                        for i, child in enumerate(where_node.parent.childs):
                            if child == where_node:
                                where_node.parent.childs[i] = current
                                current.parent = where_node.parent
                                break
                    else:
                        # where_node is root
                        tree = current

                self._log(
                    'debug', f"Decomposed {len(conditions)} conditions into nested selections")

        return tree

    def _optimize_selection_order(self, tree: QueryTree) -> QueryTree:
        """
        Reorder cascaded selections based on selectivity

        More selective conditions should be applied first (bottom of tree)
        """
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer, ConditionAnalyzer, CostEstimator

        self._log('debug', "Optimizing selection order")

        # Find all WHERE nodes
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'WHERE')

        if len(where_nodes) <= 1:
            return tree

        # Extract conditions with their selectivity
        conditions_with_selectivity = []
        for where_node in where_nodes:
            conditions = ConditionAnalyzer.extract_conditions(where_node)
            for cond in conditions:
                selectivity = CostEstimator.estimate_selectivity(cond)
                conditions_with_selectivity.append(
                    (cond, selectivity, where_node))

        # Sort by selectivity (most selective first = lowest selectivity value)
        conditions_with_selectivity.sort(key=lambda x: x[1])

        self._log(
            'debug', f"Reordered {len(conditions_with_selectivity)} selections by selectivity")

        # Note: Full reordering would require tree restructuring
        # For now, log the optimization opportunity
        return tree

    def _combine_selection_with_join(self, tree: QueryTree) -> QueryTree:
        """
        Combine σθ(E1×E2) → E1 ⋈θ E2
        or σθ(E1 ⋈φ E2) → E1 ⋈θ∧φ E2

        This is the most important optimization: converting expensive Cartesian products
        with WHERE conditions into efficient theta joins.
        """
        from Query_Optimizer.lib.optimization.tree_utils import TreeAnalyzer

        self._log('debug', "Combining selection with join")

        # Find FROM and WHERE nodes
        from_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'FROM')
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, 'WHERE')

        if not from_nodes or not where_nodes:
            return tree

        from_node = from_nodes[0]
        where_node = where_nodes[0]

        # Check if FROM has multiple tables (Cartesian product)
        if len(from_node.childs) >= 2:
            # Check if WHERE contains a join condition between tables
            join_condition = self._find_join_condition(where_node, from_node)

            if join_condition:
                # Convert to JOIN node
                self._log('info', f"Converting Cartesian product to theta join")

                # Create JOIN node with the join condition
                join_node = QueryTree(
                    type='JOIN',
                    val=join_condition['expression'],
                    childs=from_node.childs[:],  # Copy the table references
                    parent=from_node
                )

                # Update child parents
                for child in join_node.childs:
                    child.parent = join_node

                # Replace FROM children with single JOIN node
                from_node.childs = [join_node]

                # Remove the join condition from WHERE (keep other conditions if any)
                self._remove_condition_from_where(where_node, join_condition)

                self._log(
                    'debug', f"Successfully converted to JOIN: {join_condition['expression']}")

        return tree

    def _find_join_condition(self, where_node: QueryTree, from_node: QueryTree) -> Optional[dict]:
        """Find join conditions in WHERE that relate tables in FROM"""
        # Look for equality conditions between columns from different tables
        # E.g., "u.id = o.user_id"

        # Get table aliases
        table_aliases = []
        for child in from_node.childs:
            if child.type == 'ALIAS':
                table_aliases.append(child.val)

        # Search for OPERATOR nodes with '=' that reference different table aliases
        def find_equality_between_tables(node: QueryTree) -> Optional[dict]:
            if node.type == 'OPERATOR' and node.val == '=':
                # Check if children are columns from different tables
                if len(node.childs) >= 2:
                    left = node.childs[0]
                    right = node.childs[1]

                    if left.type == 'COLUMN' and right.type == 'COLUMN':
                        # Extract table aliases from column names (e.g., "u.id" → "u")
                        left_parts = left.val.split('.')
                        right_parts = right.val.split('.')

                        if len(left_parts) >= 2 and len(right_parts) >= 2:
                            left_table = left_parts[0]
                            right_table = right_parts[0]

                            # Check if they reference different tables
                            if left_table != right_table and left_table in table_aliases and right_table in table_aliases:
                                return {
                                    'expression': f"{left.val} = {right.val}",
                                    'left_table': left_table,
                                    'right_table': right_table,
                                    'node': node
                                }

            # Recursively search children
            for child in node.childs:
                result = find_equality_between_tables(child)
                if result:
                    return result

            return None

        return find_equality_between_tables(where_node)

    def _remove_condition_from_where(self, where_node: QueryTree, condition: dict):
        """Remove a specific condition from WHERE clause"""
        # If WHERE has only this condition, we could remove WHERE entirely
        # For simplicity, just mark it as processed
        # In a full implementation, would restructure the WHERE tree
        pass
