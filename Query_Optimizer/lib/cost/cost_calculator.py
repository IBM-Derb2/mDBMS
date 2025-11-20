"""
Cost Calculator
Handles calculation of query execution costs for optimization.
"""

from ...types import QueryTree

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
    if node.type in ['COLUMNS', 'FROM', 'WHERE', 'SET', 'VALUES', 'COLUMN_DEFS']:
        return 0

    # Table access cost (base cost for table scan)
    elif node.type == 'TABLE':
        # Base cost for accessing a table (statistics-based calc will override)
        return 100

    # Column reference cost (very cheap - just a reference)
    elif node.type == 'COLUMN':
        return 1

    # Literal value cost (free - just a value)
    elif node.type == 'LITERAL':
        return 0

    # Operator costs
    elif node.type == 'OPERATOR':
        return _get_operator_cost(node.val)

    # Join operation costs (expensive operations)
    elif node.type == 'JOIN':
        # Natural joins may need to match on multiple columns
        if node.val == 'NATURAL':
            return 1000  # Natural join needs column matching
        else:
            return 500  # Explicit join condition (hash join base cost)

    # DML operation costs
    elif node.type == 'SELECT':
        return 50  # Base cost for SELECT operation
    elif node.type == 'INSERT':
        return 200  # INSERT needs to update indices and maintain constraints
    elif node.type == 'UPDATE':
        return 300  # UPDATE needs to read, modify, and write + update indices
    elif node.type == 'DELETE':
        return 250  # DELETE needs to update indices and cascade

    # Default cost for unknown types
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
    if operator in ['AND', 'OR', 'NOT']:
        return 2

    # Equality comparisons (very cheap - single comparison)
    elif operator in ['=', '!=', '<>']:
        return 3

    # Range comparisons (cheap - single comparison)
    elif operator in ['<', '<=', '>', '>=']:
        return 3

    # Simple arithmetic (cheap)
    elif operator in ['+', '-']:
        return 5

    # Multiplication (moderate)
    elif operator == '*':
        return 10

    # Division/modulo (more expensive)
    elif operator in ['/', '%']:
        return 15

    # String operations (expensive - character by character)
    elif operator in ['LIKE', 'ILIKE', '~', '~*']:
        return 100

    # Set operations (moderate - involves multiple comparisons)
    elif operator in ['IN', 'NOT IN']:
        return 50

    # Range operations (moderate)
    elif operator in ['BETWEEN', 'NOT BETWEEN']:
        return 30

    # NULL checks (cheap)
    elif operator in ['IS NULL', 'IS NOT NULL']:
        return 2

    # Default for unknown operators
    else:
        return 10
