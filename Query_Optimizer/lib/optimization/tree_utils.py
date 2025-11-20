"""
Utility functions for query tree manipulation and analysis
"""

from typing import List, Set, Dict, Optional
from Query_Optimizer.query_types import QueryTree


class TreeAnalyzer:
    """Utility class for analyzing query trees"""

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
        """
        Calculate the depth of the query tree

        Args:
            tree: The root of the query tree

        Returns:
            Maximum depth of the tree
        """
        if not tree.childs:
            return 1

        max_child_depth = max(TreeAnalyzer.get_depth(child)
                              for child in tree.childs)
        return 1 + max_child_depth

    @staticmethod
    def extract_tables(tree: QueryTree) -> Set[str]:
        """
        Extract all table names referenced in the query

        Args:
            tree: The root of the query tree

        Returns:
            Set of table names
        """
        tables = set()

        # Look for FROM, JOIN nodes
        if tree.type in ['FROM', 'JOIN', 'TABLE']:
            if tree.val:
                tables.add(tree.val)

        for child in tree.childs:
            tables.update(TreeAnalyzer.extract_tables(child))

        return tables

    @staticmethod
    def extract_columns(tree: QueryTree) -> Set[str]:
        """
        Extract all column names referenced in the query

        Args:
            tree: The root of the query tree

        Returns:
            Set of column names
        """
        columns = set()

        # Look for column references
        if tree.type in ['COLUMN', 'IDENTIFIER']:
            if tree.val and tree.val != '*':
                columns.add(tree.val)

        for child in tree.childs:
            columns.update(TreeAnalyzer.extract_columns(child))

        return columns

    @staticmethod
    def has_subquery(tree: QueryTree) -> bool:
        """
        Check if the tree contains subqueries

        Args:
            tree: The root of the query tree

        Returns:
            True if subquery exists
        """
        # Look for nested SELECT nodes
        if tree.type == 'SELECT' and tree.parent is not None:
            parent = tree.parent
            if parent.type in ['FROM', 'WHERE', 'JOIN']:
                return True

        return any(TreeAnalyzer.has_subquery(child) for child in tree.childs)


class TreeManipulator:
    """Utility class for manipulating query trees"""

    @staticmethod
    def copy_tree(tree: QueryTree) -> QueryTree:
        """
        Create a deep copy of a query tree

        Args:
            tree: The tree to copy

        Returns:
            A new QueryTree with the same structure
        """
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
        """
        Replace a node in the tree with a new node

        Args:
            tree: The root of the tree
            old_node: The node to replace
            new_node: The replacement node

        Returns:
            The modified tree
        """
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
        """
        Insert a new node as parent of an existing node

        Args:
            child: The existing node
            new_parent: The new parent node to insert

        Returns:
            The new parent node
        """
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
    """Utility class for analyzing WHERE and JOIN conditions"""

    @staticmethod
    def extract_conditions(tree: QueryTree) -> List[Dict[str, any]]:
        """
        Extract all conditions from WHERE/ON clauses

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

        # Look for WHERE, ON nodes
        if tree.type in ['WHERE', 'ON', 'CONDITION']:
            condition = ConditionAnalyzer._parse_condition(tree)
            if condition:
                conditions.append(condition)

        for child in tree.childs:
            conditions.extend(ConditionAnalyzer.extract_conditions(child))

        return conditions

    @staticmethod
    def _parse_condition(node: QueryTree) -> Optional[Dict[str, any]]:
        """
        Parse a single condition node

        Returns:
            Condition dictionary or None
        """
        # Look for comparison operators in the node or its children
        if not node:
            return None

        # Check for COMPARISON type nodes
        if node.type == 'COMPARISON':
            # Extract operator, left, right from children
            if len(node.childs) >= 2:
                left = node.childs[0].val if node.childs[0] else None
                right = node.childs[1].val if len(node.childs) > 1 else None
                operator = node.val if node.val else '='

                # Extract tables from qualified names (e.g., 'users.id' -> 'users')
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

        # Simple parsing from node value if it contains operators
        if node.val and any(op in node.val for op in ['=', '>', '<', '>=', '<=', '!=', 'LIKE']):
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
        """
        Split AND conditions into separate groups

        Args:
            conditions: List of conditions

        Returns:
            List of condition groups (each group is a single condition)
        """
        # Each condition becomes its own group for decomposition
        # This enables σθ1∧θ2(E) = σθ1(σθ2(E))
        return [[cond] for cond in conditions]

    @staticmethod
    def get_tables_in_condition(condition: Dict) -> Set[str]:
        """
        Extract table names referenced in a condition

        Args:
            condition: Condition dictionary

        Returns:
            Set of table names
        """
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
        """
        Check if condition is a join condition (references multiple tables)

        Args:
            condition: Condition dictionary

        Returns:
            True if it's a join condition
        """
        tables = ConditionAnalyzer.get_tables_in_condition(condition)
        # Join condition involves columns from 2+ different tables
        return len(tables) >= 2


class CostEstimator:
    """Utility class for estimating query costs"""

    @staticmethod
    def estimate_selectivity(condition: Dict) -> float:
        """
        Estimate selectivity of a condition (fraction of rows passing)

        Args:
            condition: Condition dictionary

        Returns:
            Selectivity factor (0.0 to 1.0)
        """
        # Default heuristics based on operator
        operator = condition.get('operator', '=')

        if operator == '=':
            return 0.1  # Equality is highly selective
        elif operator in ['<', '>', '<=', '>=']:
            return 0.33  # Range queries are moderately selective
        elif operator in ['LIKE', 'IN']:
            return 0.5  # Pattern matching varies
        else:
            return 0.5  # Default

    @staticmethod
    def estimate_result_size(operation: str, input_size: int, selectivity: float = 1.0) -> int:
        """
        Estimate result size after an operation

        Args:
            operation: Type of operation ('select', 'join', 'project')
            input_size: Input size
            selectivity: Selectivity factor

        Returns:
            Estimated result size
        """
        if operation == 'select':
            return int(input_size * selectivity)
        elif operation == 'project':
            return input_size  # Projection doesn't change row count
        elif operation == 'join':
            # Simplified join size estimation
            return int(input_size * selectivity * 10)  # Rough estimate
        else:
            return input_size


# Convenience functions
def find_all_joins(tree: QueryTree) -> List[QueryTree]:
    """Find all JOIN nodes in the tree"""
    return TreeAnalyzer.find_nodes_by_type(tree, 'JOIN')


def find_all_selections(tree: QueryTree) -> List[QueryTree]:
    """Find all WHERE/selection nodes in the tree"""
    return TreeAnalyzer.find_nodes_by_type(tree, 'WHERE')


def get_all_tables(tree: QueryTree) -> Set[str]:
    """Get all tables referenced in the query"""
    return TreeAnalyzer.extract_tables(tree)


def get_all_columns(tree: QueryTree) -> Set[str]:
    """Get all columns referenced in the query"""
    return TreeAnalyzer.extract_columns(tree)
