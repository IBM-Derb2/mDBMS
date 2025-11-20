from __future__ import annotations
from typing import Union, List, Dict, Tuple, Any, Optional
import os
from b_plus_tree_index import BPlusTreeIndex
from hash_index import HashIndex
from pathlib import Path
from utils import DataRetrieval, DataWrite, DataDeletion, Rows, Statistic, IndexType
from math import ceil
from serializer import Serializer


class StorageEngine:
    DATA_FOLDER = "data"

    def __init__(
        self, data_dir: str = "", serializer: Serializer = None
    ) -> None:
        self.data_dir = data_dir
        if serializer is None:
            self.serializer = Serializer()
        else:
            self.serializer = serializer

    def read_block(self, data_retrieval: DataRetrieval) -> Rows:
        """
        kalo search_type="index", lakukan Random Access Read.
        kalo tidak, lakukan Full Scan.
        """

        table = data_retrieval.table
        BLOCK_SIZE = 1024
        schema_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table}_schema.dat"
        data_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table}.dat"

        try:
            with open(schema_file, "rb") as f:
                schema = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"File schema for {table} table is not found")

        skema = self.serializer.deserialize_schema(schema)

        # LOGIKA INDEX (Random Access Read)
        candidate_indices = None
        use_index = (
            data_retrieval.search_type == "index" 
            and data_retrieval.index_column is not None
        )

        if use_index:
            target_col = data_retrieval.index_column
            search_value = self._extract_search_value(data_retrieval.conditions, target_col)
            
            if search_value is not None:
                index_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table}_{target_col}_hash.dat"
                if os.path.exists(index_file):
                    candidate_indices = self._scan_using_hash_index(index_file, search_value)

        result_rows = Rows()
        target_columns = set(data_retrieval.column)
        wants_all_columns = "*" in target_columns or not target_columns

        # USE Index (lompat-lompat baca file)
        if candidate_indices is not None:
            row_size = self.serializer.get_row_size(skema["columns"])
            rows_per_block = BLOCK_SIZE // row_size
            
            with open(data_file, "rb") as f:
                for idx in candidate_indices:
                    # Matematika Blok untuk mencari posisi byte
                    block_idx = idx // rows_per_block
                    inner_idx = idx % rows_per_block
                    byte_offset = (block_idx * BLOCK_SIZE) + (inner_idx * row_size)
                    
                    f.seek(byte_offset) 
                    row_binary = f.read(row_size) 
                    
                    if not row_binary: continue

                    row = self.serializer.deserialize_single_row(row_binary, skema["columns"])
                    
                    if self._matches_conditions(row, data_retrieval.conditions):
                        if wants_all_columns:
                            result_rows.data.append(row)
                        else:
                            result_rows.data.append({k: v for k, v in row.items() if k in target_columns})
                        result_rows.idx.append(idx)

        # Linear Scan (Baca semua file - Fallback)
        else:
            with open(data_file, "rb") as f:
                binary_data = f.read()
            
            rows_data = self.serializer.deserialize_with_blocks(binary_data, skema["columns"])
            
            for idx, row in enumerate(rows_data):
                if self._matches_conditions(row, data_retrieval.conditions):
                    if wants_all_columns:
                        result_rows.data.append(row)
                    else:
                        result_rows.data.append({k: v for k, v in row.items() if k in target_columns})
                    result_rows.idx.append(idx)

        result_rows.rows_count = len(result_rows.data)
        return result_rows

    def _matches_conditions(self, row: dict, conditions: List) -> bool:
        """
        ngecek apakah satu row memenuhi semua kondisi di DataRetrieval.
        """

        if not conditions:
            return True

        for condition in conditions:
            column_value = row.get(condition.column)
            if column_value is None:
                return False
            if not self._evaluate_condition(column_value, condition):
                return False
        return True

    def _evaluate_condition(self, value: Union[str, int], condition) -> bool:
        """
        membandingkan dua nilai berdasarkan operator SQL sederhana
        """

        if condition.operation == "=":
            return value == condition.operand
        elif condition.operation == "<>":
            return value != condition.operand
        elif condition.operation == ">":
            return value > condition.operand
        elif condition.operation == ">=":
            return value >= condition.operand
        elif condition.operation == "<":
            return value < condition.operand
        elif condition.operation == "<=":
            return value <= condition.operand
        
        # kalau operator tidak dikenal, demi aman anggap tidak lolos
        return False

    def write_block(self, data_write: DataWrite) -> Rows:
        """
        menambah/memperbarui baris dalam tabel berdasarkan kondisi yang diberikan.

        Args:
            data_write (DataWrite): Objek yang berisi nama tabel, kolom yang akan diubah, kondisi WHERE, dan nilai baru.

        Returns:
            Rows: Objek Rows yang berisi baris yang telah diperbarui.
        """

        table = data_write.table
        schema_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table}_schema.dat"
        data_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table}.dat"

        with open(schema_file, "rb") as f:
            schema = f.read()

        skema = self.serializer.deserialize_schema(schema)

        with open(data_file, "rb") as f:
            binary_data = f.read()

        rows_data = self.serializer.deserialize_with_blocks(
            binary_data, skema["columns"]
        )

        if len(rows_data) == 0:
            return Rows()
        
        updated_rows = Rows()

        col_type = None
        for j in skema["columns"]:
            if j["name"] == data_write.column[0]:
                col_type = j["type"]
                break

        type_mapping = {
            "int": int,
            "float": float,
            "varchar": str,
            "char": str,
        }
        expected_type = type_mapping.get(col_type)

        for i in range(len(rows_data)):
            row = rows_data[i]

            if self._matches_conditions(row, data_write.conditions):
                if isinstance(data_write.new_value, list):
                    operasi = ""
                    for item in data_write.new_value:
                        if isinstance(item, (int, float)):
                            operasi += str(item)
                        else:
                            operasi += str(row.get(item, item))

                    try:
                        calc_value = eval(operasi)
                    except Exception:
                        continue

                    if isinstance(calc_value, expected_type):
                        row[data_write.column[0]] = calc_value
                else:
                    if isinstance(data_write.new_value, expected_type):
                        row[data_write.column[0]] = data_write.new_value
                
                updated_rows.data.append(row)
                updated_rows.idx.append(i)
        
        updated_rows.rows_count = len(updated_rows.data)

        final_data = {"columns": skema["columns"]}
        binary_data = self.serializer.serialize_with_blocks(rows_data, final_data)

        with open(data_file, "wb") as f:
            f.write(binary_data)

        return updated_rows
    
    def delete_block(self, data_deletion: DataDeletion) -> int:
        """
        hapus baris dari tabel berdasarkan kondisi yang diberikan. pake strategi "Read-All, Filter, Write-All".

        Args:
            data_deletion (DataDeletion): Objek yang berisi nama tabel dan kondisi WHERE.

        Returns:
            int: Jumlah baris yang berhasil dihapus.
        """

        table_name = data_deletion.table
        schema_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table_name}_schema.dat"
        data_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table_name}.dat"

        try:
            with open(schema_file, "rb") as f:
                schema_binary = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"File schema for {table_name} table is not found"
            )

        try:
            with open(data_file, "rb") as f:
                data_binary = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"File data table for {table_name} table is not found"
            )

        schema_dict = self.serializer.deserialize_schema(schema_binary)
        schema_columns = schema_dict.get("columns")
        if schema_columns is None:
            raise ValueError(
                f"Format skema untuk '{table_name}' tidak valid. Key 'columns' tidak ditemukan."
            )

        all_rows = self.serializer.deserialize_with_blocks(data_binary, schema_columns)
        if not all_rows:
            return 0

        # filter
        rows_to_keep = []
        deleted_count = 0
        has_conditions = data_deletion.conditions and len(data_deletion.conditions) > 0

        for row in all_rows:
            if not has_conditions:
                # kalo ga ada WHERE clause (DELETE FROM table;) -> hapus semua
                deleted_count += 1
            elif self._matches_conditions(row, data_deletion.conditions):
                # ada WHERE dan cocok (DELETE FROM users WHERE id=1;) -> hapus
                deleted_count += 1
            else:
                # ada WHERE tapi tidak cocok -> simpan
                rows_to_keep.append(row)

        # overwrite
        if deleted_count > 0:
            new_data_binary = self.serializer.serialize_with_blocks(
                rows_to_keep, schema_dict
            )
            with open(data_file, "wb") as f:
                f.write(new_data_binary)

        return deleted_count

    def set_index(
        self, table: str, column: str, index_type: IndexType
    ) -> None:
        schema_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table}_schema.dat"
        data_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table}.dat"

        if not os.path.exists(schema_file) or not os.path.exists(data_file):
             raise FileNotFoundError(f"Tabel {table} tidak ditemukan, tidak bisa membuat index.")

        with open(schema_file, "rb") as f:
            schema = self.serializer.deserialize_schema(f.read())
        
        with open(data_file, "rb") as f:
            rows_data = self.serializer.deserialize_with_blocks(f.read(), schema["columns"])

        if index_type == "hash" or index_type == "Hash":
            indexer = HashIndex()
            index_filename = f"{self.DATA_FOLDER}/{self.data_dir}/{table}_{column}_hash.dat"
            
            # Populate Index: Mapping Nilai -> List Index Baris
            for i, row in enumerate(rows_data):
                val = row.get(column)
                if val is not None:
                    indexer.insert(val, i)
            
            indexer.save(index_filename)
            print(f"Index Hash berhasil dibuat: {index_filename}")

        elif index_type == "b+ tree":
            pass
        
        return None

    def get_stats(self, table: str) -> Statistic:
        """
        menghitung statistik dasar dari tabel yang diberikan.

        Args:
            table (str): Nama tabel untuk menghitung statistik.

        Returns:
            Statistic: Objek Statistik yang memiliki n_r, b_r, l_r, f_r, V_a_r
        """

        block_size = 1024
        data_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table}.dat"
        schema_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table}_schema.dat"

        with open(schema_file, "rb") as f:
            schema = f.read()

        deserialized_schema = self.serializer.deserialize_schema(schema)

        # l_r - tuple size
        tuple_size = sum(
            col.get("length", 4) if col["type"] in ["varchar", "char"] else 4
            for col in deserialized_schema["columns"]
        )

        # f_r - blocking factor
        blocking_factor = block_size // tuple_size

        with open(data_file, "rb") as f:
            data = f.read()
        deserialized_data = self.serializer.deserialize_with_blocks(
            data, deserialized_schema["columns"]
        )

        # n_r - number of tuples
        n_tuples = len(deserialized_data)

        # b_r - number of blocks
        n_blocks = ceil(n_tuples / blocking_factor)

        # V_a_r - distinct values in r for attr a
        distinct_val = {}
        for col in deserialized_schema["columns"]:
            col_name = col["name"]
            distinct_val[col_name] = len(
                set(row[col_name] for row in deserialized_data)
            )
        return Statistic(n_tuples, n_blocks, tuple_size, blocking_factor, distinct_val)

    def write_schema_file(self, schema: dict) -> None:
        """
        tulis skema ke file menggunakan serializer.

        Args:
            schema (dict): Skema tabel dengan nama tabel dan kolom.
        """

        table_name = schema["table_name"]
        schema_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table_name}_schema.dat"

        import os
        os.makedirs(os.path.dirname(schema_file), exist_ok=True)

        schema_bytes = self.serializer.serialize_schema(schema)
        with open(schema_file, "wb") as f:
            f.write(schema_bytes)

    def write_data_file(self, table: str, data: list, schema: dict) -> None:
        """
        tulis data ke file menggunakan serializer.

        Args:
            table (str): Nama tabel
            data (list): Daftar baris data untuk ditulis
            schema (dict): Skema tabel dengan nama tabel dan kolom.
        """

        data_file = f"{self.DATA_FOLDER}/{self.data_dir}/{table}.dat"

        import os
        os.makedirs(os.path.dirname(data_file), exist_ok=True)

        data_bytes = self.serializer.serialize_with_blocks(data, schema)
        with open(data_file, "wb") as f:
            f.write(data_bytes)
            
    def _extract_search_value(self, conditions: Optional[List], target_col: str) -> Any:
        # [Helper] Cari nilai operand jika ada kondisi '=' pada kolom target.
        if not conditions:
            return None
        for cond in conditions:
            if cond.column == target_col and cond.operation == "=":
                return cond.operand
        return None

    def _scan_using_hash_index(self, index_path: str, search_key: Any) -> List[int]:
        # [Helper] Load file hash index dan cari key-nya
        indexer = HashIndex()
        indexer.load(index_path)
        return indexer.search(search_key)
