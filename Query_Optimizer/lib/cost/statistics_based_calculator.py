"""
Statistics-Based Cost Calculator

Enhanced cost calculator that uses database statistics for more accurate cost estimation.
This allows the optimizer to show measurable improvements.
"""

from ...types import QueryTree
from .statistics import get_statistics_manager


def calculate_node_cost_with_stats(node: QueryTree, estimated_rows: int = None) -> tuple[int, int]:
    """
    Calculate cost considering database statistics

    Returns:
        tuple(cost, estimated_rows): Total cost and estimated result rows
    """
    stats_mgr = get_statistics_manager()

    if node.type == 'SELECT':
        # Calculate FROM clause first to get base row count
        from_cost, from_rows = 0, 1000
        for child in node.childs:
            if child.type == 'FROM':
                from_cost, from_rows = calculate_node_cost_with_stats(child)

        # Calculate WHERE clause selectivity
        where_selectivity = 1.0
        where_cost = 0
        for child in node.childs:
            if child.type == 'WHERE':
                where_cost, where_selectivity = _estimate_where_selectivity(
                    child, stats_mgr)

        # Result rows after selection
        result_rows = int(from_rows * where_selectivity)

        # SELECT cost = base cost + WHERE evaluation cost
        select_cost = 50 + (from_rows * 2) + where_cost  # Cost to process rows
        total_cost = select_cost + from_cost

        # Add costs for other clauses
        for child in node.childs:
            if child.type not in ['FROM', 'WHERE']:
                child_cost, _ = calculate_node_cost_with_stats(
                    child, result_rows)
                total_cost += child_cost

        return total_cost, result_rows

    elif node.type == 'FROM':
        return _calculate_from_cost(node, stats_mgr)

    elif node.type == 'TABLE':
        table_name = node.val
        row_count = stats_mgr.get_row_count(table_name)
        # Table scan cost = rows * cost_per_row
        table_cost = row_count * 5  # 5 units per row
        return table_cost, row_count

    elif node.type == 'JOIN':
        return _calculate_join_cost(node, stats_mgr)

    elif node.type == 'OPERATOR':
        # Operator cost depends on number of rows being processed
        rows = estimated_rows if estimated_rows else 1000
        op_cost = rows * 2  # 2 units per row for operator evaluation
        return op_cost, rows

    else:
        # Default: recurse through children
        total_cost = 0
        total_rows = estimated_rows if estimated_rows else 1000
        for child in node.childs:
            child_cost, child_rows = calculate_node_cost_with_stats(
                child, estimated_rows)
            total_cost += child_cost
            if child_rows:
                total_rows = child_rows
        return total_cost, total_rows


def _calculate_from_cost(node: QueryTree, stats_mgr) -> tuple[int, int]:
    """Calculate cost of FROM clause (tables and joins)"""
    if not node.childs:
        return 0, 0

    if len(node.childs) == 1:
        # Single table
        return calculate_node_cost_with_stats(node.childs[0])

    # Multiple tables - could be Cartesian product (expensive!) or joins
    total_cost = 0
    total_rows = 1

    has_join = any(child.type == 'JOIN' for child in node.childs)

    if has_join:
        # Explicit joins - process normally
        for child in node.childs:
            child_cost, child_rows = calculate_node_cost_with_stats(child)
            total_cost += child_cost
            if child_rows:
                total_rows = child_rows
    else:
        # Multiple tables without explicit JOIN = Cartesian product (EXPENSIVE!)
        # Cost is multiplicative
        table_costs = []
        table_rows = []

        for child in node.childs:
            # Handle both direct TABLE nodes and ALIAS nodes with TABLE children
            if child.type == 'TABLE':
                cost, rows = calculate_node_cost_with_stats(child)
                table_costs.append(cost)
                table_rows.append(rows)
            elif child.type == 'ALIAS' and child.childs and child.childs[0].type == 'TABLE':
                # ALIAS node wrapping a TABLE
                cost, rows = calculate_node_cost_with_stats(child.childs[0])
                table_costs.append(cost)
                table_rows.append(rows)

        # Cartesian product: rows = product of all table rows
        total_rows = 1
        for rows in table_rows:
            total_rows *= rows

        # Cost includes reading all tables + creating Cartesian product
        total_cost = sum(table_costs) + (total_rows *
                                         10)  # 10 units per result row

    return total_cost, total_rows


def _calculate_join_cost(node: QueryTree, stats_mgr) -> tuple[int, int]:
    """Calculate cost of JOIN operation

    Uses hash join algorithm:
    - Build hash table on smaller table: O(left_rows)
    - Probe with larger table: O(right_rows)
    - Total: O(left_rows + right_rows + result_rows)

    This is MUCH more efficient than Cartesian product: O(left_rows * right_rows)
    """
    # Get left and right table statistics
    left_cost, left_rows = 0, 1000
    right_cost, right_rows = 0, 1000

    if len(node.childs) >= 2:
        left_cost, left_rows = calculate_node_cost_with_stats(node.childs[0])
        right_cost, right_rows = calculate_node_cost_with_stats(node.childs[1])

    # For equi-join (equality condition), assume foreign key relationship
    # Result size is typically equal to the larger table (each row matches once)
    # For foreign key: orders.user_id → users.id means each order has one user
    result_rows = max(left_rows, right_rows)  # Assuming FK constraint

    # Hash join cost model:
    # 1. Build hash table on smaller relation: smaller_rows * 5
    # 2. Probe with larger relation: larger_rows * 3
    # 3. Output results: result_rows * 2
    smaller_rows = min(left_rows, right_rows)
    larger_rows = max(left_rows, right_rows)

    build_cost = smaller_rows * 5
    probe_cost = larger_rows * 3
    output_cost = result_rows * 2

    join_cost = build_cost + probe_cost + output_cost

    total_cost = left_cost + right_cost + join_cost
    return total_cost, result_rows


def _estimate_where_selectivity(node: QueryTree, stats_mgr) -> tuple[int, float]:
    """
    Estimate selectivity of WHERE clause

    Returns:
        tuple(cost, selectivity): Cost to evaluate WHERE and selectivity factor
    """
    if not node.childs:
        return 0, 1.0

    condition = node.childs[0] if node.childs else None
    if not condition:
        return 0, 1.0

    # For AND conditions, multiply selectivities (more selective)
    if condition.type == 'OPERATOR' and condition.val == 'AND':
        total_cost = 0
        total_selectivity = 1.0
        for child in condition.childs:
            cost, sel = _estimate_condition_selectivity(child, stats_mgr)
            total_cost += cost
            total_selectivity *= sel  # AND conditions multiply
        return total_cost, total_selectivity

    # For OR conditions, add selectivities (less selective)
    elif condition.type == 'OPERATOR' and condition.val == 'OR':
        total_cost = 0
        total_selectivity = 0.0
        for child in condition.childs:
            cost, sel = _estimate_condition_selectivity(child, stats_mgr)
            total_cost += cost
            total_selectivity += sel  # OR conditions add
        return total_cost, min(total_selectivity, 1.0)

    else:
        return _estimate_condition_selectivity(condition, stats_mgr)


def _estimate_condition_selectivity(node: QueryTree, stats_mgr) -> tuple[int, float]:
    """Estimate selectivity of a single condition"""
    if node.type == 'OPERATOR' and node.val in ['=', '!=', '<', '<=', '>', '>=']:
        # Simple comparison condition
        # Try to extract table and column info
        selectivity = 0.1  # Default 10% selectivity
        cost = 100  # Cost to evaluate condition

        # More sophisticated: check if we can identify the column
        # For now, use heuristics based on operator
        if node.val == '=':
            selectivity = 0.1  # Equality is selective
        elif node.val in ['<', '>', '<=', '>=']:
            selectivity = 0.33  # Range queries less selective
        elif node.val == '!=':
            selectivity = 0.9  # Not equal is not selective

        return cost, selectivity

    # Default for unknown conditions
    return 50, 0.5
