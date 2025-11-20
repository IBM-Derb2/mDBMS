"""
Query Cost Calculation Module
Provides functions to calculate the execution cost of SQL queries.

Uses statistics-based cost calculation when available for more accurate estimates.
"""

from typing import Union, Optional, Tuple
import logging
from ..types import ParsedQuery
from .cost.cost_calculator import calculate_node_cost

# Try to import statistics-based calculator for detailed cost info
try:
    from .cost.statistics_based_calculator import calculate_node_cost_with_stats
    STATS_AVAILABLE = True
except ImportError:
    STATS_AVAILABLE = False


def internal_get_cost(query: Union[str, ParsedQuery], logger: Optional[logging.Logger] = None) -> int:
    """
    Menghitung biaya eksekusi dari query yang diberikan,
    dan adalah method pendukung untuk method optimize_query.

    Uses statistics-based cost calculation automatically when available.

    Args:
        query: Either a SQL query string or a ParsedQuery object
        logger: Optional logger for debugging

    Returns:
        The total cost of executing the query
    """
    # If query is a string, it needs to be parsed first by the caller
    if isinstance(query, str):
        raise TypeError(
            "internal_get_cost requires a ParsedQuery instance. Use OptimizationEngine.get_cost() for string queries.")

    parsed_query = query

    if logger:
        logger.debug(
            f"Calculating cost for query type: {parsed_query.query_tree.type}")

    # calculate_node_cost already uses statistics internally when USE_STATISTICS=True
    total_cost = calculate_node_cost(parsed_query.query_tree)

    if logger:
        logger.debug(f"Total query cost: {total_cost} (statistics-based)")

    return total_cost


def internal_get_detailed_cost(query: Union[str, ParsedQuery], logger: Optional[logging.Logger] = None) -> Tuple[int, int]:
    """
    Menghitung biaya eksekusi dan estimasi jumlah baris hasil dari query.

    Uses statistics-based cost calculation for accurate estimates of both
    execution cost and result cardinality.

    Args:
        query: Either a SQL query string or a ParsedQuery object
        logger: Optional logger for debugging

    Returns:
        Tuple of (total_cost, estimated_rows)
        - total_cost: The total cost of executing the query
        - estimated_rows: Estimated number of rows in the result set
    """
    # If query is a string, it needs to be parsed first by the caller
    if isinstance(query, str):
        raise TypeError(
            "internal_get_detailed_cost requires a ParsedQuery instance. Use OptimizationEngine for string queries.")

    parsed_query = query

    if logger:
        logger.debug(
            f"Calculating detailed cost for query type: {parsed_query.query_tree.type}")

    # Try to use statistics-based calculator for detailed info
    if STATS_AVAILABLE:
        try:
            total_cost, estimated_rows = calculate_node_cost_with_stats(
                parsed_query.query_tree)

            if logger:
                logger.debug(
                    f"Query cost: {total_cost}, Estimated rows: {estimated_rows:,}")

            return total_cost, estimated_rows
        except Exception as e:
            if logger:
                logger.warning(
                    f"Statistics-based calculation failed: {e}. Falling back to simple cost.")

    # Fallback: use simple cost calculation
    total_cost = calculate_node_cost(parsed_query.query_tree)
    estimated_rows = 1000  # Default estimate when statistics unavailable

    if logger:
        logger.debug(
            f"Query cost (fallback): {total_cost}, Estimated rows (default): {estimated_rows:,}")

    return total_cost, estimated_rows
