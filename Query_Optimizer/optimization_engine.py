

import logging
from typing import Optional, Union

from .query_types import ParsedQuery
from .lib.helpers.tokenizer import SQLTokenizer
from .lib.parsers.sql_parser import SQLParser
from .lib.optimization.optimizer import QueryOptimizer
from .lib.optimization.tree_utils import TreeManipulator
from .lib.cost.statistics import StatisticsManager


class OptimizationEngine:
    def __init__(self, storage_engine=None, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.storage_engine = storage_engine
        self.statistics_manager = StatisticsManager(storage_engine=storage_engine)
        self.optimizer = QueryOptimizer(logger=self.logger)

    def _log(self, level: str, message: str):
        if self.logger:
            log_method = getattr(self.logger, level.lower(), None)
            if log_method:
                log_method(message)

    def parse_query(self, query: str) -> ParsedQuery:
        try:
            self._log('info', f"Parsing query: {query}")

            if not query or not query.strip():
                raise ValueError("Query string cannot be empty")

            tokenizer = SQLTokenizer(query, logger=self.logger)
            tokens = tokenizer.tokenize()

            parser = SQLParser(tokens, logger=self.logger)
            query_tree = parser.parse()

            TreeManipulator.set_parent_pointers(query_tree)

            parsed_query = ParsedQuery(query_tree=query_tree, query=query)

            self._log('info', f"Successfully parsed query type: {parsed_query.query_tree.type}")

            return parsed_query

        except ValueError as e:
            self._log('error', f"Parse error: {str(e)}")
            raise
        except Exception as e:
            self._log('error', f"Unexpected error during parsing: {str(e)}")
            raise ValueError(f"Failed to parse query: {str(e)}")

    def optimize_query(self, parsed_query: ParsedQuery) -> ParsedQuery:
        if not isinstance(parsed_query, ParsedQuery):
            raise TypeError("optimize_query requires a ParsedQuery instance")

        self._log('info', f"Optimizing parsed query type: {parsed_query.query_tree.type}")

        optimized_query = self.optimizer.optimize(parsed_query)

        self._log('info', "Optimization completed")

        return optimized_query

    def get_cost(self, query: Union[str, ParsedQuery]) -> int:
        if isinstance(query, str):
            parsed_query = self.parse_query(query)
        else:
            parsed_query = query

        self._log('debug', f"Calculating cost for query type: {parsed_query.query_tree.type}")

        cost, _ = self.statistics_manager.calculate_cost(parsed_query.query_tree)

        self._log('debug', f"Total query cost: {cost}")

        return cost

    def get_detailed_cost(self, query: Union[str, ParsedQuery]) -> tuple[int, int]:
        if isinstance(query, str):
            parsed_query = self.parse_query(query)
        else:
            parsed_query = query

        self._log('debug', f"Calculating detailed cost for query type: {parsed_query.query_tree.type}")

        cost, estimated_rows = self.statistics_manager.calculate_cost(parsed_query.query_tree)

        self._log('debug', f"Total query cost: {cost}, Estimated rows: {estimated_rows:,}")

        return cost, estimated_rows
