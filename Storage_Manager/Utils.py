from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Literal

SearchType = Literal["linear", "index"]


@dataclass
class DataRetrieval:
    """
    Atribut:
    table : str
        Nama tabel yang ingin diambil datanya
    columns : list[str] | None
        List nama kolom yang ingin diambil
        None berarti ambil semua kolom (SELECT *)
    conditions : list[Condition] | None
        Kondisi seleksi (WHERE)
    search_type : "linear" | "index"
        "linear"  -> full scan ke file / semua blok
        "index"   -> B+ tree / hash
    index_column : str | None
        Kolom yang digunakan sebagai key index ketika search_type = "index"
        Kalau None, bisa fallback ke kolom di conditions[0]
    """

    table: str
    columns: Optional[List[str]] = None
    conditions: Optional[List["Condition"]] = None
    search_type: SearchType = "linear"
    index_column: Optional[str] = None

    def wants_all_columns(self) -> bool:
        return self.columns is None or len(self.columns) == 0


@dataclass
class DataDeletion:
    table: str
    conditions: Optional[List[Condition]] = None


@dataclass
class Statistic:
    def __init__(self, n_r: int, b_r: int, l_r: int, f_r: int, V_a_r: dict[str, int]):
        self.n_r = n_r
        self.b_r = b_r
        self.l_r = l_r
        self.f_r = f_r
        self.V_a_r = V_a_r
