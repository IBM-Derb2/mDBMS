

import logging
from typing import Optional, Union

from .types import ParsedQuery
from .lib.parse_query import internal_parse_query
from .lib.get_cost import internal_get_cost


class OptimizationEngine:
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Create an OptimizationEngine.

        logger: optional logging.Logger instance. If provided, engine will
        write debug/info/error messages to it.
        """
        self.logger = logger or logging.getLogger(__name__)

    def _log(self, level: str, message: str):
        """Internal logging helper method"""
        if self.logger:
            log_method = getattr(self.logger, level.lower(), None)
            if log_method:
                log_method(message)

    def parse_query(self, query: str) -> ParsedQuery:
        """
        Menerima query dalam bentuk string dan mengubahnya menjadi object yang merepresentasikan query yang telah di-parse.
        Implementasi internal dari objek parsed query sepenuhnya diserahkan kepada masing - masing kelompok.
        """
        try:
            self._log('info', f"Parsing query: {query}")

            parsed_query = internal_parse_query(query, logger=self.logger)

            self._log(
                'info', f"Successfully parsed query type: {parsed_query.query_tree.type}")

            return parsed_query

        except ValueError as e:
            self._log('error', f"Parse error: {str(e)}")
            raise
        except Exception as e:
            self._log('error', f"Unexpected error during parsing: {str(e)}")
            raise ValueError(f"Failed to parse query: {str(e)}")

    def optimize_query(self, parsed_query: ParsedQuery) -> ParsedQuery:
        """
        Perform optimization on a parsed query and return an optimized
        ParsedQuery. This method expects a ParsedQuery instance (the caller
        is responsible for parsing raw SQL text via `parse_query`).

        The optimization applies equivalence rules including:
        - Selection decomposition and reordering
        - Projection elimination
        - Join order optimization
        - Selection/projection push-down
        """
        if not isinstance(parsed_query, ParsedQuery):
            raise TypeError("optimize_query requires a ParsedQuery instance")

        self._log(
            'info', f"Optimizing parsed query type: {parsed_query.query_tree.type}")

        # Import and use the internal optimizer
        from .lib.optimize_query import internal_optimize_query

        # Apply optimization
        optimized_query = internal_optimize_query(parsed_query, self.logger)

        self._log('info', "Optimization completed")

        return optimized_query

    def get_cost(self, query: Union[str, ParsedQuery]) -> int:
        """
        Menghitung biaya eksekusi dari query yang diberikan,
        dan adalah method pendukung untuk method optimize_query.

        Args:
            query: Either a SQL query string or a ParsedQuery object

        Returns:
            The total cost of executing the query
        """
        if isinstance(query, str):
            parsed_query = self.parse_query(query)
        else:
            parsed_query = query

        self._log(
            'debug', f"Calculating cost for query type: {parsed_query.query_tree.type}")
        cost = internal_get_cost(parsed_query, self.logger)
        self._log('debug', f"Total query cost: {cost}")

        return cost
