"""
Statistics-Based Cost Calculator

Enhanced cost calculator that uses database statistics for more accurate cost estimation.
This allows the optimizer to show measurable improvements.
"""

from ...query_types import QueryTree
from globalsy.constants.query_types import QueryTypes
from .statistics import get_statistics_manager


def calculate_node_cost_with_stats(node: QueryTree, estimated_rows: int = None) -> tuple[int, int]:
    """
    Calculate cost considering database statistics

    Returns:
        tuple(cost, estimated_rows): Total cost and estimated result rows
    """
    stats_mgr = get_statistics_manager()

    if node.type == QueryTypes.SELECT:
        # Calculate FROM clause first to get base row count
        from_cost, from_rows = 0, 1000
        for child in node.childs:
            if child.type == QueryTypes.FROM:
                from_cost, from_rows = calculate_node_cost_with_stats(child)

        # Calculate WHERE clause selectivity
        where_selectivity = 1.0
        where_cost = 0
        for child in node.childs:
            if child.type == QueryTypes.WHERE:
                where_cost, where_selectivity = _estimate_where_selectivity(
                    child, stats_mgr)

        # Result rows after selection
        result_rows = int(from_rows * where_selectivity)

        # SELECT cost = base cost + WHERE evaluation cost
        select_cost = 50 + (from_rows * 2) + where_cost  # Cost to process rows
        total_cost = select_cost + from_cost

        # Add costs for other clauses
        for child in node.childs:
            if child.type not in [QueryTypes.FROM, QueryTypes.WHERE]:
                child_cost, _ = calculate_node_cost_with_stats(
                    child, result_rows)
                total_cost += child_cost

        return total_cost, result_rows

    elif node.type == QueryTypes.FROM:
        return _calculate_from_cost(node, stats_mgr)

    elif node.type == QueryTypes.TABLE:
        table_name = node.val
        row_count = stats_mgr.get_row_count(table_name)
        # Table scan cost = rows * cost_per_row
        table_cost = row_count * 5  # 5 units per row
        return table_cost, row_count

    elif node.type == QueryTypes.JOIN:
        return _calculate_join_cost(node, stats_mgr)

    elif node.type == QueryTypes.OPERATOR:
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

    has_join = any(child.type == QueryTypes.JOIN for child in node.childs)

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
            if child.type == QueryTypes.TABLE:
                cost, rows = calculate_node_cost_with_stats(child)
                table_costs.append(cost)
                table_rows.append(rows)
            elif child.type == 'ALIAS' and child.childs and child.childs[0].type == QueryTypes.TABLE:
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

    Join cardinality estimation formulas:
    - If R ∩ S = {A} is a key for R: size = n_s (each S tuple matches at most one R tuple)
    - If R ∩ S = {A} is a key for S: size = n_r (each R tuple matches at most one S tuple)
    - If R ∩ S = {A} is not a key for either: size = (n_r * n_s) / max(V(A,r), V(A,s))
    - If no common attributes (Cartesian product): size = n_r * n_s
    """
    # Get left and right table statistics
    left_cost, left_rows = 0, 1000
    right_cost, right_rows = 0, 1000

    if len(node.childs) >= 2:
        left_cost, left_rows = calculate_node_cost_with_stats(node.childs[0])
        right_cost, right_rows = calculate_node_cost_with_stats(node.childs[1])

    # Estimate join result size based on join type
    # For natural joins or equi-joins, use more accurate formulas
    if node.val == 'NATURAL' or _has_join_condition(node):
        # Try to detect if join attribute is a key
        # Heuristic: if one table is much smaller and has close to unique values,
        # it's likely a key (e.g., users.id in orders JOIN users)

        # If smaller table has rows ≈ distinct values on join column, it's likely a key
        # In that case, result size ≈ larger table size
        # Left is much smaller (likely dimension table)
        if left_rows < right_rows * 0.1:
            result_rows = right_rows  # Each right row matches one left row
        elif right_rows < left_rows * 0.1:  # Right is much smaller
            result_rows = left_rows  # Each left row matches one right row
        else:
            # Both tables similar size - use formula for non-key joins
            # size = (n_r * n_s) / max(V(A,r), V(A,s))
            # Without V(A,r), use heuristic: assume V(A,r) ≈ min(n_r, n_s)
            # This gives: result ≈ max(n_r, n_s)
            result_rows = max(left_rows, right_rows)

            # Apply selectivity factor for potential filtering in join condition
            result_rows = int(result_rows * 0.8)  # Assume 80% match
    else:
        # No explicit join condition - Cartesian product (very expensive!)
        result_rows = left_rows * right_rows

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


def _has_join_condition(node: QueryTree) -> bool:
    """Check if join has an explicit join condition"""
    # Check if join node has ON or USING clause in its children
    return len(node.childs) >= 3  # Left, Right, and Condition


def _estimate_where_selectivity(node: QueryTree, stats_mgr) -> tuple[int, float]:
    """
    Estimate selectivity of WHERE clause using database theory formulas

    Formulas:
    - Conjunction (AND): s1 * s2 * ... * sn (multiply selectivities)
    - Disjunction (OR): 1 - (1-s1) * (1-s2) * ... * (1-sn)
    - Negation (NOT): 1 - selectivity

    Returns:
        tuple(cost, selectivity): Cost to evaluate WHERE and selectivity factor
    """
    if not node.childs:
        return 0, 1.0

    condition = node.childs[0] if node.childs else None
    if not condition:
        return 0, 1.0

    # For AND conditions, use conjunction formula: multiply selectivities
    if condition.type == QueryTypes.OPERATOR and condition.val == 'AND':
        total_cost = 0
        selectivities = []
        for child in condition.childs:
            cost, sel = _estimate_condition_selectivity(child, stats_mgr)
            total_cost += cost
            selectivities.append(sel)

        # Use proper conjunction formula
        total_selectivity = stats_mgr.estimate_conjunction_selectivity(
            selectivities)
        return total_cost, total_selectivity

    # For OR conditions, use disjunction formula: 1 - (1-s1)*(1-s2)*...*(1-sn)
    elif condition.type == QueryTypes.OPERATOR and condition.val == 'OR':
        total_cost = 0
        selectivities = []
        for child in condition.childs:
            cost, sel = _estimate_condition_selectivity(child, stats_mgr)
            total_cost += cost
            selectivities.append(sel)

        # Use proper disjunction formula
        total_selectivity = stats_mgr.estimate_disjunction_selectivity(
            selectivities)
        return total_cost, total_selectivity

    # For NOT conditions, use negation formula
    elif condition.type == QueryTypes.OPERATOR and condition.val == 'NOT':
        if condition.childs:
            cost, sel = _estimate_condition_selectivity(
                condition.childs[0], stats_mgr)
            # Use negation formula: 1 - selectivity
            negated_selectivity = stats_mgr.estimate_negation_selectivity(sel)
            return cost, negated_selectivity
        return 0, 1.0

    else:
        return _estimate_condition_selectivity(condition, stats_mgr)


def _estimate_condition_selectivity(node: QueryTree, stats_mgr) -> tuple[int, float]:
    """Estimate selectivity of a single condition using database theory"""
    if node.type == QueryTypes.OPERATOR and node.val in ['=', '!=', '<', '<=', '>', '>=']:
        # Simple comparison condition
        cost = 100  # Cost to evaluate condition

        # Try to extract column and value from condition
        table_name = None
        column_name = None
        value = None

        # Try to find COLUMN node and LITERAL node
        for child in node.childs:
            if child.type == QueryTypes.COLUMN:
                column_name = child.val
                # Try to infer table name from column's children or context
                if child.childs and child.childs[0].type == QueryTypes.TABLE:
                    table_name = child.childs[0].val
            elif child.type == QueryTypes.LITERAL:
                value = child.val

        # If we found column info, use statistics-based estimation
        if column_name:
            # Try common table names if table not specified
            if not table_name:
                for table in ['users', 'orders', 'products', 'categories']:
                    if stats_mgr.get_table_stats(table):
                        table_stats = stats_mgr.get_table_stats(table)
                        if column_name in table_stats.column_stats:
                            table_name = table
                            break

            if table_name:
                selectivity = stats_mgr.estimate_selectivity(
                    table_name, column_name, node.val, value
                )
                return cost, selectivity

        # Fall back to heuristics if we can't use statistics
        if node.val == '=':
            # Equality is selective (assume ~10 distinct values)
            selectivity = 0.1
        elif node.val in ['<', '>', '<=', '>=']:
            selectivity = 0.33  # Range queries less selective
        elif node.val == '!=':
            selectivity = 0.9  # Not equal is not selective
        else:
            selectivity = 0.5

        return cost, selectivity

    # Default for unknown conditions
    return 50, 0.5
