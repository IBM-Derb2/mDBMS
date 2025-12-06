from typing import Optional
import logging
from globalsy.classes.query_tree import QueryTree
from globalsy.constants.query_types import QueryTypes
from globalsy.constants.query_operators import QueryOperators
from ..base_rule import OptimizationRule
from ..tree_utils import TreeAnalyzer, ConditionAnalyzer


class SelectionRule(OptimizationRule):
    """Yang handle optimasi seleksi: pushdown selection"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__(logger)

    def can_apply(self, tree: QueryTree) -> bool:
        if tree.type != QueryTypes.PROJECTION:
            self._log('debug', "Not a PROJECTION (RA node), skipping")
            return False

        if self._has_conjunctive_condition(tree):
            self._log('debug', "Has conjunctive condition")
            return True

        if self._has_cascaded_selections(tree):
            self._log('debug', "Has cascaded selections")
            return True

        if self._has_selection_over_join_or_product(tree):
            self._log('debug', "Has selection over join/product")
            return True

        self._log('debug', "No applicable selection optimizations found")
        return False

    def apply(self, tree: QueryTree) -> QueryTree:
        self._log('info', f"Applying selection optimization with heuristic rules")

        if self._has_selection_over_join_or_product(tree):
            self._log(
                'info', "Heuristic: Converting Cartesian product + WHERE to theta join")
            tree = self._combine_selection_with_join(tree)

        if self._has_conjunctive_condition(tree):
            self._log(
                'info', "Heuristic: Decomposing AND conditions for early selection")
            tree = self._decompose_conjunctive_selection(tree)

        if self._has_cascaded_selections(tree):
            self._log(
                'info', "Heuristic: Reordering selections by selectivity (most restrictive first)")
            tree = self._optimize_selection_order(tree)

        return tree

    def _has_conjunctive_condition(self, tree: QueryTree) -> bool:

        # cari WHERE nodes atau SELECTION_STMT nodes
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.WHERE)
        selection_nodes = TreeAnalyzer.find_nodes_by_type(
            tree, QueryTypes.SELECTION_STMT)
        all_selection_nodes = where_nodes + selection_nodes

        for where_node in all_selection_nodes:
            # kalo ada AND di val
            if where_node.val and QueryOperators.AND in where_node.val.upper():
                return True

            # kalau ada AND di childs
            and_nodes = TreeAnalyzer.find_nodes_by_type(
                where_node, QueryOperators.AND)
            if and_nodes:
                return True

            # kalau ada lebih dari 1 kondisi di childs
            condition_children = [
                c for c in where_node.childs if c.type in ['COMPARISON', 'CONDITION']]
            if len(condition_children) > 1:
                return True

        return False

    def _has_cascaded_selections(self, tree: QueryTree) -> bool:
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.WHERE)
        selection_nodes = TreeAnalyzer.find_nodes_by_type(
            tree, QueryTypes.SELECTION_STMT)
        all_selection_nodes = where_nodes + selection_nodes

        # kalau ada lebih dari 1 WHERE node, pasti cascaded
        if len(all_selection_nodes) > 1:
            return True

        # cek di dalam WHERE node, ada WHERE lagi ga
        for where_node in all_selection_nodes:
            for child in where_node.childs:
                nested = TreeAnalyzer.find_nodes_by_type(
                    child, QueryTypes.WHERE)
                nested += TreeAnalyzer.find_nodes_by_type(
                    child, QueryTypes.SELECTION_STMT)
                if nested:
                    return True

        return False

    def _has_selection_over_join_or_product(self, tree: QueryTree) -> bool:
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.WHERE)
        selection_nodes = TreeAnalyzer.find_nodes_by_type(
            tree, QueryTypes.SELECTION_STMT)
        all_selection_nodes = where_nodes + selection_nodes

        if not all_selection_nodes:
            return False

        # cek kalau ada JOIN atau THETA_JOIN atau CROSS_JOIN
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.JOIN)
        theta_join_nodes = TreeAnalyzer.find_nodes_by_type(
            tree, QueryTypes.THETA_JOIN)
        cross_join_nodes = TreeAnalyzer.find_nodes_by_type(
            tree, QueryTypes.CROSS_JOIN)

        all_joins = join_nodes + theta_join_nodes + cross_join_nodes

        if all_joins:
            self._log(
                'debug', f"Found {len(all_joins)} join/cross-join nodes with selection")
            return True

        # cari FROM node
        from_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.FROM)
        if from_nodes:
            from_node = from_nodes[0]
            # cek Cartesian product: multiple tables pada FROM tanpa JOIN
            if len(from_node.childs) >= 2:
                self._log(
                    'debug', f"Found Cartesian product: {len(from_node.childs)} tables in FROM without JOIN")
                return True

        return False

    def _decompose_conjunctive_selection(self, tree: QueryTree) -> QueryTree:
        self._log('debug', "Decomposing conjunctive selection")

        # cek WHERE nodes dan SELECTION_STMT dengan multiple conditions
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.WHERE)
        selection_nodes = TreeAnalyzer.find_nodes_by_type(
            tree, QueryTypes.SELECTION_STMT)
        all_selection_nodes = where_nodes + selection_nodes

        for where_node in all_selection_nodes:

            conditions = ConditionAnalyzer.extract_conditions(where_node)

            # jika multiple conditions, decompose
            if len(conditions) > 1:
                # nested WHERE node, mulai dari bottom (innermost)
                current = where_node.childs[0] if where_node.childs else None

                if current:
                    # generate WHERE node tiap condition
                    for condition in reversed(conditions):
                        new_where = QueryTree(
                            type=QueryTypes.WHERE,
                            val=condition.get('expression', str(condition)),
                            childs=[current] if current else [],
                            parent=None
                        )
                        if current:
                            current.parent = new_where
                        current = new_where

                    if where_node.parent:
                        for i, child in enumerate(where_node.parent.childs):
                            if child == where_node:
                                where_node.parent.childs[i] = current
                                current.parent = where_node.parent
                                break
                    else:
                        # jika where_node itu root
                        tree = current

                self._log(
                    'debug', f"Decomposed {len(conditions)} conditions into nested selections")

        return tree

    def _optimize_selection_order(self, tree: QueryTree) -> QueryTree:
        self._log('debug', "Optimizing selection order")

        selection_nodes = TreeAnalyzer.find_nodes_by_type(
            tree, QueryTypes.SELECTION_STMT)

        if len(selection_nodes) <= 1:
            return tree

        selectivity_map = {}
        for sel_node in selection_nodes:
            if not sel_node.childs or len(sel_node.childs) < 2:
                continue

            condition = sel_node.childs[1]
            selectivity = self._estimate_condition_selectivity(condition)
            selectivity_map[id(sel_node)] = selectivity

        nested_selections = []
        current = tree
        while current and current.type == QueryTypes.SELECTION_STMT:
            nested_selections.append(current)
            current = current.childs[0] if current.childs else None

        if len(nested_selections) <= 1:
            return tree

        sorted_selections = sorted(
            nested_selections, key=lambda n: selectivity_map.get(id(n), 0.5))

        base = sorted_selections[0].childs[0] if sorted_selections[0].childs else None

        new_root = None
        current_node = None

        for sel_node in sorted_selections:
            if not sel_node.childs or len(sel_node.childs) < 2:
                continue

            condition = sel_node.childs[1]

            new_sel = QueryTree(
                type=QueryTypes.SELECTION_STMT,
                val=None,
                childs=[base, condition],
                parent=None
            )

            if current_node:
                current_node.childs[0] = new_sel
                new_sel.parent = current_node
            else:
                new_root = new_sel

            current_node = new_sel
            base = new_sel

        if new_root:
            self._log(
                'debug', f"Reordered {len(nested_selections)} selections by selectivity")
            return new_root

        return tree

    def _estimate_condition_selectivity(self, condition_node: QueryTree) -> float:
        if condition_node.type == QueryTypes.OPERATOR:
            if condition_node.val == QueryOperators.EQ:
                return 0.1
            elif condition_node.val in [QueryOperators.LT, QueryOperators.GT]:
                return 0.33
            elif condition_node.val == QueryOperators.NEQ:
                return 0.9
        return 0.5

    def _combine_selection_with_join(self, tree: QueryTree) -> QueryTree:
        self._log('debug', "Combining selection with join")

        # Find SELECTION_STMT (which contains the WHERE condition) and CROSS_JOIN nodes
        selection_nodes = TreeAnalyzer.find_nodes_by_type(
            tree, QueryTypes.SELECTION_STMT)
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.WHERE)
        cross_join_nodes = TreeAnalyzer.find_nodes_by_type(
            tree, QueryTypes.CROSS_JOIN)

        all_selection_nodes = selection_nodes + where_nodes

        if not all_selection_nodes or not cross_join_nodes:
            self._log('debug', "No selection or cross join nodes found")
            return tree

        # Work with the first cross join we find
        cross_join = cross_join_nodes[0]
        selection_node = all_selection_nodes[0]

        # Check if selection has a join condition between the tables in cross join
        join_condition_node = self._find_join_condition_in_selection(
            selection_node, cross_join)

        if join_condition_node:
            self._log(
                'info', f"Converting CROSS_JOIN to THETA_JOIN with condition")

            # Change CROSS_JOIN to THETA_JOIN and add the join condition as a child
            cross_join.type = QueryTypes.THETA_JOIN

            # Keep the tables as first children, add join condition
            if join_condition_node not in cross_join.childs:
                cross_join.childs.append(join_condition_node)
                join_condition_node.parent = cross_join

            self._log('debug', f"Successfully converted to THETA_JOIN")

        return tree

    def _find_join_condition_in_selection(self, selection_node: QueryTree, cross_join: QueryTree) -> Optional[QueryTree]:
        """Find an equality condition between two tables in the selection"""
        # Get table aliases from cross join
        table_aliases = []
        for child in cross_join.childs:
            if child.type == QueryTypes.ALIAS:
                if child.val:
                    table_aliases.append(child.val)
                elif child.alias:
                    table_aliases.append(child.alias)

        def find_equality_condition(node: QueryTree) -> Optional[QueryTree]:
            """Recursively search for equality between different tables"""
            if node.type == QueryTypes.OPERATOR and node.val == QueryOperators.EQ:
                # Check if both sides are columns from different tables
                if len(node.childs) >= 2:
                    left = node.childs[0]
                    right = node.childs[1]

                    if left.type == QueryTypes.COLUMN and right.type == QueryTypes.COLUMN:
                        # Extract table aliases from column references
                        left_val = left.val if left.val else ""
                        right_val = right.val if right.val else ""

                        left_parts = left_val.split('.')
                        right_parts = right_val.split('.')

                        if len(left_parts) >= 2 and len(right_parts) >= 2:
                            left_table = left_parts[0]
                            right_table = right_parts[0]

                            # Check if this is a join between two different tables
                            if left_table != right_table:
                                self._log(
                                    'debug', f"Found join condition: {left_val} = {right_val}")
                                return node

            # Recursively check children
            for child in node.childs:
                result = find_equality_condition(child)
                if result:
                    return result

            return None

        return find_equality_condition(selection_node)

    def _remove_condition_from_where(self, where_node: QueryTree, condition: dict):
        if not where_node or not where_node.childs or 'node' not in condition:
            return

        condition_to_remove = condition['node']

        if not where_node.childs:
            return

        where_condition = where_node.childs[0]

        if where_condition == condition_to_remove:
            if where_node.parent:
                parent = where_node.parent
                if where_node in parent.childs:
                    parent.childs.remove(where_node)
            return

        if where_condition.type == QueryTypes.OPERATOR and where_condition.val == QueryOperators.AND:
            new_children = [
                c for c in where_condition.childs if c != condition_to_remove]

            if len(new_children) == 0:
                if where_node.parent:
                    parent = where_node.parent
                    if where_node in parent.childs:
                        parent.childs.remove(where_node)
            elif len(new_children) == 1:
                where_node.childs = new_children
            else:
                where_condition.childs = new_children
