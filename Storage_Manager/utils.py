from dataclasses import dataclass, field
from typing import List, Optional, Dict, Literal, Union, Any

SearchMode = Literal["linear", "index"]
OperationType = Literal['=', '<>', '>', '>=', '<', '<=']
IndexType = Literal["b+ tree", "hash"]


@dataclass
class Rows:
    data: Any = field(default_factory=list)
    rows_count: int = 0
    idx: List[int] = field(default_factory=list)


@dataclass
class Condition:
    column: str
    operation: OperationType
    operand: Union[str, int]


@dataclass
class DataRetrieval:
    table: str
    column: list[str]
    conditions: Optional[list[Condition]] = None
    search_type: SearchMode = "linear"
    index_column: Optional[str] = None 


@dataclass
class DataWrite:
    table: str
    column: List[str]
    conditions: List[Condition]
    new_value: Any


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
