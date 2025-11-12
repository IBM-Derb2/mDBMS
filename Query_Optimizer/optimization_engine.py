

import logging
from typing import Optional, Union

from .types import ParsedQuery, QueryTree
from .lib.parse_query import internal_parse_query


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

        Note: optimization logic is currently a no-op and simply returns the
        provided ParsedQuery. Real optimization (rule-based or GA) should be
        implemented here in the future.
        """
        if not isinstance(parsed_query, ParsedQuery):
            raise TypeError("optimize_query requires a ParsedQuery instance")

        # Simple pass-through for now. Log the action for visibility.
        self._log(
            'info', f"Optimizing parsed query type: {parsed_query.query_tree.type}")
        # TODO: replace with actual optimization logic
        return parsed_query

    def get_cost(self, query: Union[str, ParsedQuery]) -> int:
        """
        Menghitung biaya eksekusi dari query yang diberikan,
        dan adalah method pendukung untuk method optimize_query.
        """
        if isinstance(query, str):
            parsed_query = self.parse_query(query)
        else: parsed_query = query
        return self._calculate_node_cost(parsed_query.query_tree)
    
    def _calculate_node_cost(self, node: QueryTree) -> int:
        """
        Menghitung biaya eksekusi dari sebuah node dalam pohon query secara rekursif.
        Implementasi spesifik dari perhitungan biaya tergantung pada jenis node
        dan atribut-atributnya.
        """
        node_cost = self._get_operation_cost(node)
        children_cost = sum(self._calculate_node_cost(child) for child in node.children)
        return node_cost + children_cost
    
    def _get_operation_cost(self, node: QueryTree) -> int:
        """
        Mendapatkan biaya operasi untuk jenis node tertentu.
        Implementasi spesifik dari biaya tergantung pada jenis node.
        """
        if node.type in ['COLUMNS', 'FROM', 'WHERE', 'SET', 'VALUES', 'COLUMN_DEFS']:
            return 0
        elif node.type == 'TABLE':
            return 50 #Placeholder Value
        elif node.type == 'COLUMN':
            return 1
        elif node.type == 'LITERAL':
            return 0
        elif node.type == 'OPERATOR':
            if node.val in ['AND', 'OR']:
                return 50 #Placeholder Value
            elif node.val in ['=', '!=', '<', '<=', '>', '>=', '<>']:
                return 50 #Placeholder Value
            elif node.val in ['+', '-', '*', '/', '%']:
                return 50
            else: #IN, BETWEEN, LIKE, ETC
                return 50 #Placeholder Value
        elif node.type == 'JOIN':
            if node.val == 'NATURAL':
                return 500 #Placeholder Value
            else:
                return 300 #Placeholder Value
        elif node.type == 'SELECT':
            return 50
        elif node.type == 'INSERT':
            return 100
        elif node.type == 'UPDATE':
            return 150
        elif node.type == 'DELETE':
            return 150
        else: return 1
