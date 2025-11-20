from typing import Optional
import logging
from ..query_types import ParsedQuery
from .optimization import QueryOptimizer


def internal_optimize_query(
    parsed_query: ParsedQuery,
    logger: Optional[logging.Logger] = None
) -> ParsedQuery:
    """
    Melakukan optimasi pada parsed query berdasarkan aturan optimisasi,
    kemudian mengembalikan query yang telah dipotimize.

    Args:
        parsed_query: The parsed query to optimize
        logger: Optional logger instance

    Returns:
        Optimized ParsedQuery

    Note:
        Implementasi menggunakan genetic algorithm akan mendapatkan nilai bonus.
    """
    # Create optimizer instance
    optimizer = QueryOptimizer(logger=logger)

    # Apply optimization rules
    optimized_query = optimizer.optimize(parsed_query)

    return optimized_query
