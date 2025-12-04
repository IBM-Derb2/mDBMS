from dataclasses import dataclass, field
from typing import List


@dataclass
class Rows:
    data: List[dict] = field(default_factory=list)
    rows_count: int = 0
    message: str = ""
    idx: List[int] = field(default_factory=list)
    table_name: str = ""  # Table name metadata for JOIN operations
