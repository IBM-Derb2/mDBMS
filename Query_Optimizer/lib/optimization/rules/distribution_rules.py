from typing import Optional, Set
import logging
from globalsy.classes.query_tree import QueryTree
from globalsy.constants.query_types import QueryTypes
from ..base_rule import OptimizationRule
from ..tree_utils import TreeAnalyzer, TreeManipulator, ConditionAnalyzer


class DistributionRule(OptimizationRule):
    """Yang handle optimasi distribusi: pushdown, selection dan projection"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        super().__init__(logger)

    def can_apply(self, tree: QueryTree) -> bool:
        if tree.type != QueryTypes.PROJECTION:
            return False
        return (self._has_selection_over_join(tree) or
                self._has_projection_over_join(tree))

    def apply(self, tree: QueryTree) -> QueryTree:
        self._log('info', f"Applying distribution optimization")
        if self._has_selection_over_join(tree):
            tree = self._push_selection_down(tree)
        if self._has_projection_over_join(tree):
            tree = self._push_projection_down(tree)
        return tree

    def _has_selection_over_join(self, tree: QueryTree) -> bool:
        where_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.WHERE)
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.JOIN)

        return len(where_nodes) > 0 and len(join_nodes) > 0

    def _has_projection_over_join(self, tree: QueryTree) -> bool:
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.JOIN)

        if not join_nodes:
            return False
        column_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.COLUMN)
        return len(column_nodes) > 0

    def _push_selection_down(self, tree: QueryTree) -> QueryTree:
        self._log('debug', "Pushing selection down")
        conditions = self._extract_where_conditions(tree)

        # conditions dari relation
        relation_conditions = self._classify_conditions_by_relation(conditions)
        optimized_tree = self._apply_pushed_selections(tree, relation_conditions)
        return optimized_tree

    def _push_projection_down(self, tree: QueryTree) -> QueryTree:
        self._log('debug', "Pushing projection down")
        required_columns = self._extract_required_columns(tree)

        # cek join attributes
        join_attributes = self._extract_join_attributes(tree)
        optimized_tree = self._apply_pushed_projections(tree, required_columns, join_attributes)
        return optimized_tree

    def _extract_where_conditions(self, tree: QueryTree) -> list:
        conditions = ConditionAnalyzer.extract_conditions(tree)

        self._log('debug', f"Extracted {len(conditions)} WHERE conditions")
        return conditions

    def _classify_conditions_by_relation(self, conditions: list) -> dict:
        relation_conditions = {}
        join_conditions = []

        for condition in conditions:
            tables = ConditionAnalyzer.get_tables_in_condition(condition)

            if len(tables) == 1:
                table = list(tables)[0]
                if table not in relation_conditions:
                    relation_conditions[table] = []
                relation_conditions[table].append(condition)
                self._log('debug', f"Condition for table {table}: {condition.get('expression', condition)}")

            elif len(tables) > 1:
                join_conditions.append(condition)
                self._log('debug', f"Join condition involving {tables}: {condition.get('expression', condition)}")

        if join_conditions:
            relation_conditions['__join__'] = join_conditions

        return relation_conditions

    def _apply_pushed_selections(self, tree: QueryTree, relation_conditions: dict) -> QueryTree:
        if not relation_conditions:
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

                curr = target_node.parent
                already_exists = False
                while curr:
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
        columns = TreeAnalyzer.extract_columns(tree)

        self._log('debug', f"Required columns: {columns}")
        return columns

    def _extract_join_attributes(self, tree: QueryTree) -> Set[str]:
        join_attributes = set()
        join_nodes = TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.JOIN)

        for join_node in join_nodes:
            on_nodes = TreeAnalyzer.find_nodes_by_type(join_node, QueryTypes.ON)
            for on_node in on_nodes:
                conditions = ConditionAnalyzer.extract_conditions(on_node)
                for cond in conditions:
                    if 'left' in cond and cond['left']:
                        join_attributes.add(str(cond['left']))
                    if 'right' in cond and cond['right']:
                        join_attributes.add(str(cond['right']))

        self._log('debug', f"Join attributes: {join_attributes}")
        return join_attributes

    def _apply_pushed_projections(self, tree: QueryTree,
                                  required_columns: Set[str],
                                  join_attributes: Set[str]) -> QueryTree:
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
                    t_part = col.split('.', 1)[0]
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
                    type=QueryTypes.PROJECTION,
                    val=proj_val,
                    childs=[],
                    parent=None
                )
                TreeManipulator.insert_node_above(
                    target_node, new_project_node)

        return tree
