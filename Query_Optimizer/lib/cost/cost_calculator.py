"""
Cost Calculator
Handles calculation of query execution costs for optimization.
"""

from ...query_types import QueryTree
from globalsy.constants.query_types import QueryTypes
from globalsy.constants.query_operators import QueryOperators

# Feature flag to enable statistics-based costing
USE_STATISTICS = True

if USE_STATISTICS:
    try:
        from .statistics_based_calculator import calculate_node_cost_with_stats
    except ImportError:
        USE_STATISTICS = False


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
    # Use statistics-based calculation if available
    if USE_STATISTICS:
        try:
            cost, _ = calculate_node_cost_with_stats(node)
            return cost
        except Exception as e:
            # Fall back to simple calculation if stats fail
            print(f"⚠️ Stats-based cost calculation failed: {e}")
            import traceback
            traceback.print_exc()

    # Simple calculation without statistics
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
    if node.type in [QueryTypes.COLUMNS, QueryTypes.SET, QueryTypes.VALUES, QueryTypes.COLUMN_DEFS,
                     QueryTypes.FROM, QueryTypes.WHERE, QueryTypes.ON,
                     QueryTypes.TABLE, QueryTypes.COLUMN, QueryTypes.IDENTIFIER,
                     QueryTypes.CONDITION, QueryTypes.COMPARISON]:
        return 0

    # Table access cost (base cost for table scan)
    elif node.type == QueryTypes.TABLE:
        return 100
    elif node.type == QueryTypes.COLUMN:
        return 1
    elif node.type == QueryTypes.IDENTIFIER:
        return 1
    elif node.type == QueryTypes.CONDITION or node.type == QueryTypes.COMPARISON:
        return 2
    elif node.type == QueryTypes.ON:
        return 2
    elif node.type == QueryTypes.JOIN:
        if node.val == QueryTypes.NATURAL:
            return 1000
        else:
            return 500
    elif node.type == QueryTypes.SELECT:
        return 50
    elif node.type == QueryTypes.INSERT:
        return 200
    elif node.type == QueryTypes.UPDATE:
        return 300
    elif node.type == QueryTypes.DELETE:
        return 250
    elif node.type == QueryTypes.CREATE:
        return 400
    elif node.type == QueryTypes.DROP:
        return 350
    elif node.type == QueryTypes.ALTER:
        return 320
    elif node.type == QueryTypes.TRUNCATE:
        return 330
    elif node.type == QueryTypes.MERGE:
        return 340
    # Literal value cost (free - just a value)
    elif hasattr(QueryTypes, 'LITERAL') and node.type == QueryTypes.LITERAL:
        return 0
    # Operator costs
    elif hasattr(QueryTypes, 'OPERATOR') and node.type == QueryTypes.OPERATOR:
        return _get_operator_cost(node.val)
    else:
        return 1


def _get_operator_cost(operator: str) -> int:
    """
    Get the cost for a specific operator.

    Costs reflect relative computational complexity:
    - Logical operators: cheap (just boolean operations)
    - Comparisons: cheap (single comparison)
    - Arithmetic: cheap to moderate (depending on operation)
    - String operations: more expensive
    - Special operators: varies by complexity

    Args:
        operator: The operator string (e.g., 'AND', '=', '+', etc.)

    Returns:
        Cost of the operator (relative units)
    """
    # Logical operators (cheap - just boolean logic)
    if operator in [QueryOperators.AND, QueryOperators.OR, QueryOperators.NOT]:
        return 2

    # Equality comparisons (very cheap - single comparison)
    elif operator in [QueryOperators.EQ, QueryOperators.NEQ, QueryOperators.ALT_NEQ]:
        return 3

    # Range comparisons (cheap - single comparison)
    elif operator in [QueryOperators.LT, QueryOperators.LTE, QueryOperators.GT, QueryOperators.GTE]:
        return 3

    # Simple arithmetic (cheap)
    elif operator in [QueryOperators.PLUS, QueryOperators.MINUS]:
        return 5

    # Multiplication (moderate)
    elif operator == QueryOperators.MULTIPLY:
        return 10

    # Division/modulo (more expensive)
    elif operator in [QueryOperators.DIVIDE, QueryOperators.MODULO]:
        return 15

    # String operations (expensive - character by character)
    elif operator in [QueryOperators.LIKE, QueryOperators.ILIKE, '~', '~*']:
        return 100

    # Set operations (moderate - involves multiple comparisons)
    elif operator in [QueryOperators.IN, QueryOperators.NOT_IN]:
        return 50

    # Range operations (moderate)
    elif operator in [QueryOperators.BETWEEN, QueryOperators.NOT_BETWEEN]:
        return 30

    # NULL checks (cheap)
    elif operator in [QueryOperators.IS_NULL, QueryOperators.IS_NOT_NULL]:
        return 2

    # Default for unknown operators
    else:
        return 10
