"""
Query Cost Calculation Module
Provides functions to calculate the execution cost of SQL queries.
"""

from typing import Union, Optional
import logging
from ..types import ParsedQuery
from .cost.cost_calculator import calculate_node_cost


def internal_get_cost(query: Union[str, ParsedQuery], logger: Optional[logging.Logger] = None) -> int:
    """
    Menghitung biaya eksekusi dari query yang diberikan,
    dan adalah method pendukung untuk method optimize_query.

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

    total_cost = calculate_node_cost(parsed_query.query_tree)

    if logger:
        logger.debug(f"Total query cost: {total_cost}")

    return total_cost
