from dataclasses import dataclass
from typing import List, Optional, Dict, Literal

SearchMode = Literal["linear", "index"]

@dataclass
class DataRetrieval:
    table: str
    column: list[str]
    conditions: Optional[list[Condition]] = None
    search_type: SearchMode = "linear"
    index_column: Optional[str] = None 


@dataclass
class DataDeletion:
    table: str
    conditions: Optional[List[Condition]] = None


@dataclass
class Statistic:
    n_r: int
    b_r: int
    l_r: int
    f_r: int
    V_a_r: Dict[str, int]
