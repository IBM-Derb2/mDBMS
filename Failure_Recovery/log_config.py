from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Union

# tipe aksi yang bisa terjadi
class ActionType(Enum):
    START = 0
    WRITE = 1
    COMMIT = 2
    ABORT = 3
# mock  dari data yang dikirim oelh query processor
@dataclass
class MockExecutionResult:
    transaction_id: int
    query: str
    # data bisa berisi apa aj, tapi utk write kita asumsikan datanya baru
    data: Any 

# moxk dari laporan perubahan yang dikasi oleh orang 2 (buffer manager) stlh dia memproces data
@dataclass
class MockChangeReport:
    table_name: str
    pk_value: Any
    old_data: Union[dict, None] = None # data lama (utk update/delelte)
    new_data: Union[dict, None] = None # data baru (utk update/insert)

