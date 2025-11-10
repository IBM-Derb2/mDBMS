from typing import Union
from ..types import ParsedQuery


def internal_get_cost(query: Union[str, ParsedQuery]) -> int:
    """
    Menghitung biaya eksekusi dari query yang diberikan,
    dan adalah method pendukung untuk method optimize_query.
    """
