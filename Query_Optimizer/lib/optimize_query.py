from typing import Union
from ..types import ParsedQuery


def internal_optimize_query(query: Union[str, ParsedQuery]) -> ParsedQuery:
    """
    Melakukan optimasi pada parsed query berdasarkan aturan optimisasi,
    kemudian mengembalikan query yang telah dipotimize.
    Implementasi menggunakan genetic algorithm akan mendapatkan nilai bonus.
    """
    pass
