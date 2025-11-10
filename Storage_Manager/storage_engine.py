from __future__ import annotations
from typing import Union, Dict, Tuple, Any, Iterable
from index_type_enum import IndexTypeEnum
from b_plus_tree_index import BPlusTreeIndex
from hash_index import HashIndex
from pathlib import Path
from Utils import DataRetrieval, DataDeletion, Rows

class StorageEngine:
    def __init__(self, data_dir: str = "data", serializer: Any | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.serializer = serializer
        # key: (table, column) -> value: index object (BPlusTreeIndex / HashIndex)
        self.indexes: Dict[Tuple[str, str], Union[BPlusTreeIndex, HashIndex]] = {}

    def read_block(self, data_retrieval: DataRetrieval) -> Rows:
        """
        TODO (buat pengembangan lanjut):
        kalau data_retrieval.search_type == "index" dan index tersedia,
        gunakan index untuk memperkecil candidate rows (bukan full scan).
        """
        table = data_retrieval.table

        if self.serializer is None:
            raise RuntimeError("Serializer belum di-set di StorageEngine")
        
        raw_rows: Iterable[dict] = self.serializer.iter_rows(table)

        result_rows = []

        for row in raw_rows:
            if not self._match_conditions(row, data_retrieval):
                continue

            if data_retrieval.wants_all_columns():
                projected = row
            else:
                projected = {
                    col: row.get(col, None) for col in data_retrieval.columns
                }

            result_rows.append(projected)

        return Rows(data=result_rows)

    def _match_conditions(self, row: dict, data_retrieval: DataRetrieval) -> bool:
        """
        ngecek apakah satu row memenuhi semua kondisi di DataRetrieval.
        """
        if not data_retrieval.conditions:
            # tidak ada WHERE -> selalu lolos
            return True

        for cond in data_retrieval.conditions:
            column = cond.column
            op = cond.operation
            operand_raw = cond.operand

            value = row.get(column, None)

            # sementara operand & value dibandingkan apa adanya.
            # nanti bisa ditambah casting tipe (int, float, dll) sesuai schema.
            operand = operand_raw

            if not self._compare(value, op, operand):
                return False

        return True

    @staticmethod
    def _compare(left: Any, op: str, right: Any) -> bool:
        """
        membandingkan dua nilai berdasarkan operator SQL sederhana
        """
        if op == "=":
            return left == right
        if op in ("<>", "!="):
            return left != right
        if op == "<":
            return left < right
        if op == ">":
            return left > right
        if op == "<=":
            return left <= right
        if op == ">=":
            return left >= right
        # kalau operator tidak dikenal, demi aman anggap tidak lolos
        return False
    
    def delete_block(self, data_deletion: DataDeletion) -> int:
        """
        hapus baris dari tabel berdasarkan kondisi yang diberikan. pake strategi "Read-All, Filter, Write-All".

        Args:
            data_deletion (DataDeletion): Objek yang berisi nama tabel dan kondisi WHERE.
        Returns:
            int: Jumlah baris yang berhasil dihapus.
        """
        if self.serializer is None:
            raise RuntimeError("Serializer belum di-set")

        table_name = data_deletion.table
        schema_path = self.data_dir / f"{table_name}_schema.dat"
        data_path = self.data_dir / f"{table_name}.dat"

        # baca data
        try:
            schema_binary = schema_path.read_bytes()
            data_binary = data_path.read_bytes()
        except FileNotFoundError:
            raise FileNotFoundError(f"File schema/data untuk tabel '{table_name}' tidak ditemukan di '{self.data_dir}'")

        # Deserialize (Ubah biner ke list of dict)
        schema_dict = self.serializer.deserialize_schema(schema_binary) # Asumsi: deserialize_schema bakal return dict seperti: {"table_name": "...", "columns": [...]}
        schema_columns = schema_dict.get("columns") 
        if schema_columns is None:
             raise ValueError(f"Format skema untuk '{table_name}' tidak valid. Key 'columns' tidak ditemukan.")

        all_rows = self.serializer.deserialize_with_blocks(data_binary, schema_columns)
        if not all_rows:
            return 0  

        # Filter 
        rows_to_keep = []
        deleted_count = 0
        has_conditions = data_deletion.conditions and len(data_deletion.conditions) > 0

        for row in all_rows:
            matches = False
            if has_conditions:
                matches = self._match_conditions(row, data_deletion.conditions)
            
            if not has_conditions:
                # kalo ga ada WHERE clause (DELETE FROM table;) -> hapus semua
                deleted_count += 1
            elif matches:
                # ada WHERE dan cocok (DELETE FROM users WHERE id=1;) -> hapus
                deleted_count += 1
            else:
                # ada WHERE tapi tidak cocok -> simpan 
                rows_to_keep.append(row)

        # Overwrite
        if deleted_count > 0:
            new_data_binary = self.serializer.serialize_with_blocks(rows_to_keep, schema_dict)
            data_path.write_bytes(new_data_binary)

        return deleted_count

    def set_index(self, table: str, column: str, index_type:Union[str | IndexTypeEnum]) -> None:
        """
        table: table name to be indexed
        column: column name to be indexed
        index_type: index thats gonna be used, either (IndexTypeEnum.B_PLUS_TREE or "B+ Tree") or (IndexTypeEnum.HASH or "Hash")
        """
        if index_type.lower() not in ["b+ tree", "hash"]:
            raise ValueError("index_type should be 'b+ tree' or 'hash'") 
        if isinstance(index_type, str):
            index_type = index_type.lower()

        # TODO: Load data 

        if index_type in [IndexTypeEnum.B_PLUS_TREE, "b+ tree"]:
            indexer = BPlusTreeIndex()
            # TODO: do indexing, depends on data format
            pass 
        elif index_type in [IndexTypeEnum.HASH, "hash"]:
            indexer = HashIndex()
            # TODO: do indexing, depends on data format
            pass

        return None
