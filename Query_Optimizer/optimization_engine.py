

import logging
from typing import Optional, Union

from .types import ParsedQuery


class OptimizationEngine:
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Create an OptimizationEngine.

        logger: optional logging.Logger instance. If provided, engine will
        write debug/info/error messages to it.
        """
        self.logger = logger or logging.getLogger(__name__)

    def parse_query(self, query: str) -> ParsedQuery:
        """
        Menerima query dalam bentuk string dan mengubahnya menjadi object yang merepresentasikan query yang telah di-parse.
        Implementasi internal dari objek parsed query sepenuhnya diserahkan kepada masing - masing kelompok.
        """
        pass

    def optimize_query(self, query: Union[str, ParsedQuery]) -> ParsedQuery:
        """
        Melakukan optimasi pada parsed query berdasarkan aturan optimisasi,
        kemudian mengembalikan query yang telah dipotimize.
        Implementasi menggunakan genetic algorithm akan mendapatkan nilai bonus.
        """
        pass

    def get_cost(self, query: Union[str, ParsedQuery]) -> int:
        """
        Menghitung biaya eksekusi dari query yang diberikan,
        dan adalah method pendukung untuk method optimize_query.
        """
        pass
