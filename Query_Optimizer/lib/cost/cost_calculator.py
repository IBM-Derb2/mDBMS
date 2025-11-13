"""
Cost Calculator
Handles calculation of query execution costs for optimization.
"""

from ...types import QueryTree


def calculate_node_cost(node: QueryTree) -> int:
    """
    Menghitung biaya eksekusi dari sebuah node dalam pohon query secara rekursif.
    Implementasi spesifik dari perhitungan biaya tergantung pada jenis node
    dan atribut-atributnya.

    Args:
        node: QueryTree node to calculate cost for

    Returns:
        Total cost of the node including its children
    """
    node_cost = get_operation_cost(node)
    children_cost = sum(calculate_node_cost(child) for child in node.childs)
    return node_cost + children_cost


def get_operation_cost(node: QueryTree) -> int:
    """
    Mendapatkan biaya operasi untuk jenis node tertentu.
    Implementasi spesifik dari biaya tergantung pada jenis node.

    Args:
        node: QueryTree node to get operation cost for

    Returns:
        Cost of the operation for this node type
    """
    # Container nodes with no intrinsic cost
    if node.type in ['COLUMNS', 'FROM', 'WHERE', 'SET', 'VALUES', 'COLUMN_DEFS']:
        return 0

    # Table access cost
    elif node.type == 'TABLE':
        return 50  # Placeholder Value

    # Column reference cost
    elif node.type == 'COLUMN':
        return 1

    # Literal value cost
    elif node.type == 'LITERAL':
        return 0

    # Operator costs
    elif node.type == 'OPERATOR':
        return _get_operator_cost(node.val)

    # Join operation costs
    elif node.type == 'JOIN':
        if node.val == 'NATURAL':
            return 500  # Placeholder Value
        else:
            return 300  # Placeholder Value

    # DML operation costs
    elif node.type == 'SELECT':
        return 50
    elif node.type == 'INSERT':
        return 100
    elif node.type == 'UPDATE':
        return 150
    elif node.type == 'DELETE':
        return 150

    # Default cost for unknown types
    else:
        return 1


def _get_operator_cost(operator: str) -> int:
    """
    Get the cost for a specific operator.

    Args:
        operator: The operator string (e.g., 'AND', '=', '+', etc.)

    Returns:
        Cost of the operator
    """
    # Logical operators
    if operator in ['AND', 'OR']:
        return 50  # Placeholder Value

    # Comparison operators
    elif operator in ['=', '!=', '<', '<=', '>', '>=', '<>']:
        return 50  # Placeholder Value

    # Arithmetic operators
    elif operator in ['+', '-', '*', '/', '%']:
        return 50

    # Special operators (IN, BETWEEN, LIKE, etc.)
    else:
        return 50  # Placeholder Value
