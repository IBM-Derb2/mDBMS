"""
Utility functions for query tree manipulation and analysis
"""

from typing import List, Set, Dict, Optional
from globalsy.classes.query_tree import QueryTree
from globalsy.constants.query_types import QueryTypes
from globalsy.constants.query_operators import QueryOperators


class TreeAnalyzer:
    @staticmethod
    def find_nodes_by_type(tree: QueryTree, node_type: str) -> List[QueryTree]:
        """
        Find all nodes of a specific type in the tree

        Args:
            tree: The root of the query tree
            node_type: The type of nodes to find (e.g., 'JOIN', 'WHERE', 'SELECT')

        Returns:
            List of QueryTree nodes matching the type
        """

        result = []

        if tree.type == node_type:
            result.append(tree)

        for child in tree.childs:
            result.extend(TreeAnalyzer.find_nodes_by_type(child, node_type))

        return result

    @staticmethod
    def get_depth(tree: QueryTree) -> int:

        if not tree.childs:
            return 1

        max_child_depth = max(TreeAnalyzer.get_depth(child)
                              for child in tree.childs)
        return 1 + max_child_depth

    @staticmethod
    def extract_tables(tree: QueryTree) -> Set[str]:

        tables = set()

        # Look for FROM, JOIN nodes
        if tree.type in [QueryTypes.FROM, QueryTypes.JOIN, QueryTypes.TABLE]:
            if tree.val:
                tables.add(tree.val)

        for child in tree.childs:
            tables.update(TreeAnalyzer.extract_tables(child))

        return tables

    @staticmethod
    def extract_columns(tree: QueryTree) -> Set[str]:

        columns = set()

        # cek referensi kolom
        if tree.type in [QueryTypes.COLUMN, QueryTypes.IDENTIFIER]:
            if tree.val and tree.val != QueryOperators.MULTIPLY:
                columns.add(tree.val)

        for child in tree.childs:
            columns.update(TreeAnalyzer.extract_columns(child))

        return columns

    @staticmethod
    def has_subquery(tree: QueryTree) -> bool:

        # cek kalo ada nested SELECT
        if tree.type == QueryTypes.SELECT and tree.parent is not None:
            parent = tree.parent
            if parent.type in [QueryTypes.FROM, QueryTypes.WHERE, QueryTypes.JOIN]:
                return True

        return any(TreeAnalyzer.has_subquery(child) for child in tree.childs)


class TreeManipulator:
    """Utility class for manipulating query trees"""

    @staticmethod
    def set_parent_pointers(tree: QueryTree, parent: Optional[QueryTree] = None) -> QueryTree:

        tree.parent = parent
        for child in tree.childs:
            TreeManipulator.set_parent_pointers(child, tree)
        return tree

    @staticmethod
    def copy_tree(tree: QueryTree) -> QueryTree:

        new_tree = QueryTree(
            type=tree.type,
            val=tree.val,
            childs=[],
            parent=None
        )

        for child in tree.childs:
            new_child = TreeManipulator.copy_tree(child)
            new_child.parent = new_tree
            new_tree.childs.append(new_child)

        return new_tree

    @staticmethod
    def replace_node(tree: QueryTree, old_node: QueryTree, new_node: QueryTree) -> QueryTree:

        if tree == old_node:
            new_node.parent = tree.parent
            return new_node

        for i, child in enumerate(tree.childs):
            if child == old_node:
                new_node.parent = tree
                tree.childs[i] = new_node
            else:
                tree.childs[i] = TreeManipulator.replace_node(
                    child, old_node, new_node)

        return tree

    @staticmethod
    def insert_node_above(child: QueryTree, new_parent: QueryTree) -> QueryTree:

        old_parent = child.parent

        # Set up new parent
        new_parent.childs = [child]
        new_parent.parent = old_parent

        # Update child
        child.parent = new_parent

        # Update old parent if it exists
        if old_parent:
            for i, c in enumerate(old_parent.childs):
                if c == child:
                    old_parent.childs[i] = new_parent
                    break

        return new_parent


class ConditionAnalyzer:

    @staticmethod
    def extract_conditions(tree: QueryTree) -> List[Dict[str, any]]:
        """
        Ekstrak kondisi dari tree

        Args:
            tree: The root of the query tree

        Returns:
            List of condition dictionaries with structure:
            {
                'type': 'comparison',
                'left': 'column_name',
                'operator': '=',
                'right': 'value',
                'tables': ['table1', 'table2']
            }
        """

        conditions = []

        # cek node kondisi WHERE
        if tree.type in [QueryTypes.WHERE, QueryTypes.ON, QueryTypes.CONDITION]:
            condition = ConditionAnalyzer._parse_condition(tree)
            if condition:
                conditions.append(condition)

        for child in tree.childs:
            conditions.extend(ConditionAnalyzer.extract_conditions(child))

        return conditions

    @staticmethod
    def _parse_condition(node: QueryTree) -> Optional[Dict[str, any]]:

        if not node:
            return None

        # cek COMPARISON node
        if node.type == QueryTypes.COMPARISON:
    
            if len(node.childs) >= 2:
                left = node.childs[0].val if node.childs[0] else None
                right = node.childs[1].val if len(node.childs) > 1 else None
                operator = node.val if node.val else QueryOperators.EQ

                # table dengan referensi kolom
                tables = set()
                if left and '.' in left:
                    tables.add(left.split('.')[0])
                if right and '.' in str(right) and not right.replace('.', '').isdigit():
                    tables.add(right.split('.')[0])

                return {
                    'type': 'comparison',
                    'left': left,
                    'operator': operator,
                    'right': right,
                    'tables': list(tables),
                    'node': node
                }

        # simple expression condition
        if node.val and any(op in node.val for op in [QueryOperators.EQ, QueryOperators.GT, QueryOperators.LT, QueryOperators.GTE, QueryOperators.LTE, QueryOperators.NEQ, QueryOperators.LIKE]):
            tables = set()
            for part in node.val.split():
                if '.' in part:
                    tables.add(part.split('.')[0])

            return {
                'type': 'expression',
                'expression': node.val,
                'tables': list(tables),
                'node': node
            }

        return None

    @staticmethod
    def split_conjunctive_conditions(conditions: List[Dict]) -> List[List[Dict]]:

        # Each condition becomes its own group for decomposition
        # This enables σθ1∧θ2(E) = σθ1(σθ2(E))
        return [[cond] for cond in conditions]

    @staticmethod
    def get_tables_in_condition(condition: Dict) -> Set[str]:

        tables = set()

        if 'tables' in condition:
            tables.update(condition['tables'])

        # Also check left and right operands for table references
        if 'left' in condition and condition['left'] and '.' in str(condition['left']):
            tables.add(str(condition['left']).split('.')[0])
        if 'right' in condition and condition['right'] and '.' in str(condition['right']):
            if not str(condition['right']).replace('.', '').isdigit():
                tables.add(str(condition['right']).split('.')[0])

        return tables

    @staticmethod
    def is_join_condition(condition: Dict) -> bool:

        tables = ConditionAnalyzer.get_tables_in_condition(condition)
        # Join condition involves columns from 2+ different tables
        return len(tables) >= 2


class CostEstimator:
    """Utility class for estimating query costs"""

    @staticmethod
    def estimate_selectivity(condition: Dict) -> float:

        # default
        operator = condition.get('operator', '=')

        if operator == '=':
            return 0.1  # equality, highly selective
        elif operator in [QueryOperators.GT, QueryOperators.LT, QueryOperators.GTE, QueryOperators.LTE]:
            return 0.33  # range queries
        elif operator in [QueryOperators.LIKE, QueryOperators.IN]:
            return 0.5  # moderate selectivity
        else:
            return 0.5  # Default

    @staticmethod
    def estimate_result_size(operation: str, input_size: int, selectivity: float = 1.0) -> int:

        if operation == QueryTypes.SELECT:
            return int(input_size * selectivity)
        elif operation == QueryTypes.PROJECTION:
            return input_size
        elif operation == QueryTypes.JOIN:
            return int(input_size * selectivity * 10)  # Rough estimate
        else:
            return input_size


def find_all_joins(tree: QueryTree) -> List[QueryTree]:
    return TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.JOIN)


def find_all_selections(tree: QueryTree) -> List[QueryTree]:
    return TreeAnalyzer.find_nodes_by_type(tree, QueryTypes.WHERE)


def get_all_tables(tree: QueryTree) -> Set[str]:
    return TreeAnalyzer.extract_tables(tree)


def get_all_columns(tree: QueryTree) -> Set[str]:
    return TreeAnalyzer.extract_columns(tree)
