from __future__ import annotations
from typing import Union, List, Any, Optional
from math import ceil
import os
import glob

from .b_plus_tree_index import BPlusTreeIndex
from .hash_index import HashIndex
from .serializer import Serializer
from .utils import *


class StorageEngine:

    DATA_FOLDER = "data"
    BLOCK_SIZE = 1024

    TYPE_DEFAULTS = {
        "int": 0,
        "float": 0.0,
        "varchar": "",
        "char": "",
    }

    TYPE_MAPPING = {
        "int": int,
        "float": float,
        "varchar": str,
        "char": str,
    }

    def __init__(self, data_dir: str = "", serializer: Serializer = None, frm=None, cc_manager=None) -> None:
        self.data_dir = data_dir
        if serializer is None:
            self.serializer = Serializer()
        else:
            self.serializer = serializer
        self.frm = frm
        self.cc_manager = cc_manager

    # core crud

    def read_block(self, data_retrieval: DataRetrieval) -> Rows:

        table = data_retrieval.table
        schema_file = self._get_schema_path(table)
        data_file = self._get_data_path(table)

        try:
            with open(schema_file, "rb") as f:
                schema = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"File schema for {table} table is not found")

        schema_dict = self.serializer.deserialize_schema(schema)

        candidate_indices = None
        use_index = (
            data_retrieval.search_type == "index"
            and data_retrieval.index_column is not None
        )

        if use_index:
            target_col = data_retrieval.index_column
            search_value = self._extract_search_value(
                data_retrieval.conditions, target_col)

            if search_value is not None:
                hash_index_file = self._get_index_path(
                    table, target_col, "hash")
                if os.path.exists(hash_index_file):
                    candidate_indices = self._scan_using_hash_index(
                        hash_index_file, search_value)
                else:
                    btree_index_file = self._get_index_path(
                        table, target_col, "btree")
                    if os.path.exists(btree_index_file):
                        candidate_indices = self._scan_using_btree_index(
                            btree_index_file, search_value)

        result_rows = Rows()
        target_columns = set(data_retrieval.column)
        wants_all_columns = "*" in target_columns or not target_columns

        # index-based random access read
        if candidate_indices is not None:
            row_size = self.serializer.get_row_size(schema_dict["columns"])
            rows_per_block = self.BLOCK_SIZE // row_size

            with open(data_file, "rb") as f:
                for idx in candidate_indices:

                    # kalkulasi offset
                    block_idx = idx // rows_per_block
                    inner_idx = idx % rows_per_block
                    byte_offset = (block_idx * self.BLOCK_SIZE) + \
                        (inner_idx * row_size)

                    f.seek(byte_offset)
                    row_binary = f.read(row_size)

                    if not row_binary:
                        continue

                    row = self.serializer.deserialize_single_row(
                        row_binary, schema_dict["columns"])
                    row = {k.lower(): v for k, v in row.items()}

                    if self._matches_conditions(row, data_retrieval.conditions):
                        if wants_all_columns:
                            result_rows.data.append(row)
                        else:
                            result_rows.data.append(
                                {k: v for k, v in row.items() if k in target_columns})
                        result_rows.idx.append(idx)

        # full table scan (fallback)
        else:
            # pk columns untuk buffer-disk merge
            pk_columns = [col["name"].lower()
                          for col in schema_dict["columns"] if col.get("primary_key")]
            if not pk_columns:
                pk_columns = [schema_dict["columns"][0]["name"].lower()]

            buffered_rows_map = {}
            deleted_pk_tuples = set()
            for key, buffered_row in self.frm.buffer_manager.buffer_data.items():
                if buffered_row.table_name == table:
                    pk_lower = {k.lower(): v for k, v in buffered_row.primary_key_value.items()}
                    pk_tuple = tuple(sorted(pk_lower.items()))
                    if buffered_row.is_deleted:
                        deleted_pk_tuples.add(pk_tuple)
                    else:
                        buffered_rows_map[pk_tuple] = buffered_row.data

            with open(data_file, "rb") as f:
                binary_data = f.read()

            rows_data = self.serializer.deserialize_with_blocks(
                binary_data, schema_dict["columns"])

            # merge buffer dengan disk
            merged_rows = []
            processed_buffer_keys = set()

            for disk_row in rows_data:
                row_lower = {k.lower(): v for k, v in disk_row.items()}
                pk_value = {pk_col: row_lower[pk_col] for pk_col in pk_columns}
                pk_tuple = tuple(sorted(pk_value.items()))

                if pk_tuple in deleted_pk_tuples:
                    # dihapus di buffer
                    continue
                elif pk_tuple in buffered_rows_map:
                    # pakai data buffer
                    merged_rows.append(buffered_rows_map[pk_tuple])
                    processed_buffer_keys.add(pk_tuple)
                else:
                    # pakai data disk
                    merged_rows.append(disk_row)

            # tambah baris dari buffer yang belum ada di disk
            for pk_tuple, buffered_data in buffered_rows_map.items():
                if pk_tuple not in processed_buffer_keys:
                    merged_rows.append(buffered_data)

            # project
            for idx, row in enumerate(merged_rows):
                row = {k.lower(): v for k, v in row.items()}

                if self._matches_conditions(row, data_retrieval.conditions):
                    if wants_all_columns:
                        result_rows.data.append(row)
                    else:
                        result_rows.data.append(
                            {k: v for k, v in row.items() if k in target_columns})
                    result_rows.idx.append(idx)

        result_rows.rows_count = len(result_rows.data)
        result_rows.table_name = table
        return result_rows

    def write_block(self, data_write: DataWrite) -> int:

        table = data_write.table
        schema_file = self._get_schema_path(table)
        data_file = self._get_data_path(table)

        with open(schema_file, "rb") as f:
            schema = f.read()

        schema_dict = self.serializer.deserialize_schema(schema)

        with open(data_file, "rb") as f:
            binary_data = f.read()

        rows_data = self.serializer.deserialize_with_blocks(
            binary_data, schema_dict["columns"])

        updated_rows = Rows()

        modified_columns = set(
            data_write.column) if data_write.column else set()

        col_type = None
        if data_write.column:
            for col in schema_dict["columns"]:
                col_name_lower = col["name"].lower()
                target_col_lower = data_write.column[0].lower()
                if col_name_lower == target_col_lower:
                    col_type = col["type"]
                    break

        expected_type = self.TYPE_MAPPING.get(col_type)

        # INSERT (no conditions)
        if not data_write.conditions:
            new_row = {}

            for col in schema_dict["columns"]:
                col_name = col["name"]
                col_type = col["type"]
                new_row[col_name] = self.TYPE_DEFAULTS.get(col_type, None)

            if isinstance(data_write.new_value, list):
                # tidak ada spesifikasi kolom, anggap sesuai urutan di schema
                if not data_write.column:
                    for i, col in enumerate(schema_dict["columns"]):
                        if i < len(data_write.new_value):
                            value = data_write.new_value[i]
                            col_name = col["name"]
                            col_type = col["type"]
                            expected_type = self.TYPE_MAPPING.get(col_type)
                            coerced_value = self._coerce_type(value, expected_type, col_type)
                            new_row[col_name] = coerced_value
                else:
                    for i, col_name in enumerate(data_write.column):
                        if i < len(data_write.new_value):
                            value = data_write.new_value[i]
                            col_schema = next(
                                (c for c in schema_dict["columns"] if c["name"].lower() == col_name.lower()), None)
                            if col_schema:
                                expected_type = self.TYPE_MAPPING.get(
                                    col_schema["type"])
                                coerced_value = self._coerce_type(value, expected_type, col_schema["type"])
                                new_row[col_schema["name"]] = coerced_value
                            else:
                                new_row[col_name] = value
            else:
                if data_write.column:
                    value = data_write.new_value
                    col_name = data_write.column[0]
                    
                    col_schema = next(
                        (c for c in schema_dict["columns"] if c["name"].lower() == col_name.lower()), None)
                    if col_schema:
                        expected_type = self.TYPE_MAPPING.get(
                            col_schema["type"])
                        coerced_value = self._coerce_type(value, expected_type, col_schema["type"])
                        new_row[col_schema["name"]] = coerced_value
                    else:
                        new_row[col_name] = value

            # cek duplikasi di disk
            pk_columns = [col["name"] for col in schema_dict["columns"]
                         if col.get("primary_key", False)]

            # jika tidak ada pk, anggap kolom pertama sbg pk
            if not pk_columns:
                pk_columns = [schema_dict["columns"][0]["name"]]

            for existing_row in rows_data:
                is_duplicate = all(
                    existing_row.get(pk_col) == new_row.get(pk_col)
                    for pk_col in pk_columns
                )
                if is_duplicate:
                    pk_values = {pk_col: new_row.get(pk_col) for pk_col in pk_columns}
                    raise ValueError(
                        f"Primary key violation: Record with {pk_values} already exists in table '{table}'"
                    )

            # cek duplikasi di buffer
            pk_value_dict = {pk_col.lower(): new_row.get(pk_col) for pk_col in pk_columns}
            buffered_row = self.frm.get_buffered_row(table, pk_value_dict)
            if buffered_row is not None:
                pk_values = {pk_col: new_row.get(pk_col) for pk_col in pk_columns}
                raise ValueError(
                    f"Primary key violation: Record with {pk_values} already exists in buffer for table '{table}'"
                )

            pk_value_dict = {pk_col: new_row.get(pk_col) for pk_col in pk_columns}

            transaction_id = getattr(data_write, 'transaction_id', 0)
            self.frm.buffer_manager.write_block(
                transaction_id=transaction_id,
                table_name=table,
                pk_value=pk_value_dict,
                new_data=new_row
            )

            updated_rows.data.append(new_row)
            new_idx = len(rows_data)
            updated_rows.idx.append(new_idx)

        # UPDATE (dengan conditions)
        else:
            # pk for buffer
            pk_columns = [col["name"] for col in schema_dict["columns"]
                         if col.get("primary_key", False)]
            if not pk_columns:
                pk_columns = [schema_dict["columns"][0]["name"]]

            # merge buffer dengan disk
            pk_columns_lower = [pk.lower() for pk in pk_columns]
            buffered_rows_map = {}
            deleted_pk_tuples = set()

            for key, buffered_row in self.frm.buffer_manager.buffer_data.items():
                if buffered_row.table_name == table:
                    pk_lower = {k.lower(): v for k, v in buffered_row.primary_key_value.items()}
                    pk_tuple = tuple(sorted(pk_lower.items()))
                    if buffered_row.is_deleted:
                        deleted_pk_tuples.add(pk_tuple)
                    else:
                        buffered_rows_map[pk_tuple] = buffered_row.data

            merged_rows = []
            processed_buffer_keys = set()

            for disk_row in rows_data:
                row_lower = {k.lower(): v for k, v in disk_row.items()}
                pk_value = {pk_col: row_lower[pk_col] for pk_col in pk_columns_lower}
                pk_tuple = tuple(sorted(pk_value.items()))

                if pk_tuple in deleted_pk_tuples:
                    continue
                elif pk_tuple in buffered_rows_map:
                    merged_rows.append(buffered_rows_map[pk_tuple])
                    processed_buffer_keys.add(pk_tuple)
                else:
                    merged_rows.append(disk_row)

            # tambah baris dari buffer yang belum ada di disk
            for pk_tuple, buffered_data in buffered_rows_map.items():
                if pk_tuple not in processed_buffer_keys:
                    merged_rows.append(buffered_data)

            transaction_id = getattr(data_write, 'transaction_id', 0)

            for i, row in enumerate(merged_rows):
                if self._matches_conditions(row, data_write.conditions):
                    target_col_original = self._get_case_insensitive(
                        row, data_write.column[0], value_only=False)
                    if not target_col_original:
                        continue

                    old_values = {target_col_original: row.get(
                        target_col_original)}

                    updated_row = row.copy()

                    if isinstance(data_write.new_value, list):
                        # handle arithmetic expressions: ['GPA', '*', 1.1]
                        try:
                            calc_value = self._evaluate_expression(
                                data_write.new_value, row)
                        except Exception:
                            continue

                        coerced_value = self._coerce_type(calc_value, expected_type, col_type)
                        updated_row[target_col_original] = coerced_value
                    else:
                        coerced_value = self._coerce_type(data_write.new_value, expected_type, col_type)
                        updated_row[target_col_original] = coerced_value

                    pk_value_dict = {pk_col: updated_row.get(pk_col) for pk_col in pk_columns}
                    self.frm.buffer_manager.write_block(
                        transaction_id=transaction_id,
                        table_name=table,
                        pk_value=pk_value_dict,
                        new_data=updated_row
                    )

                    updated_rows.data.append(updated_row)
                    updated_rows.idx.append(i)

        updated_rows.rows_count = len(updated_rows.data)

        return updated_rows.rows_count

    def delete_block(self, data_deletion: DataDeletion) -> int:

        table_name = data_deletion.table
        schema_file = self._get_schema_path(table_name)
        data_file = self._get_data_path(table_name)

        try:
            with open(schema_file, "rb") as f:
                schema_binary = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"File schema for {table_name} table is not found")

        try:
            with open(data_file, "rb") as f:
                data_binary = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"File data table for {table_name} table is not found")

        schema_dict = self.serializer.deserialize_schema(schema_binary)
        schema_columns = schema_dict.get("columns")
        if schema_columns is None:
            raise ValueError(
                f"Invalid schema format for '{table_name}'. Key 'columns' not found.")

        # pk columns
        pk_columns = [col["name"] for col in schema_dict["columns"]
                     if col.get("primary_key", False)]
        if not pk_columns:
            pk_columns = [schema_dict["columns"][0]["name"]]

        all_rows = self.serializer.deserialize_with_blocks(
            data_binary, schema_columns)
        if not all_rows:
            return 0

        deleted_count = 0
        has_conditions = data_deletion.conditions and len(
            data_deletion.conditions) > 0

        transaction_id = getattr(data_deletion, 'transaction_id', 0)

        for i, row in enumerate(all_rows):
            should_delete = False

            if not has_conditions:
                should_delete = True
            elif self._matches_conditions(row, data_deletion.conditions):
                should_delete = True

            if should_delete:
                pk_value_dict = {pk_col: row.get(pk_col) for pk_col in pk_columns}
                self.frm.buffer_manager.delete_block(
                    transaction_id=transaction_id,
                    table_name=table_name,
                    pk_value=pk_value_dict,
                    old_data=row
                )
                deleted_count += 1

        return deleted_count

    # DDL

    def write_table(self, table_name: str, schema: dict) -> None:

        schema_file = self._get_schema_path(table_name)
        data_file = self._get_data_path(table_name)

        if os.path.exists(schema_file) or os.path.exists(data_file):
            raise FileExistsError(f"Table '{table_name}' already exists")

        os.makedirs(os.path.dirname(schema_file), exist_ok=True)
        schema_bytes = self.serializer.serialize_schema(schema)
        with open(schema_file, "wb") as f:
            f.write(schema_bytes)

        empty_data = self.serializer.serialize_with_blocks([], schema)
        with open(data_file, "wb") as f:
            f.write(empty_data)

    def delete_table(self, table_name: str) -> None:

        schema_file = self._get_schema_path(table_name)
        data_file = self._get_data_path(table_name)

        if not os.path.exists(schema_file) and not os.path.exists(data_file):
            raise FileNotFoundError(f"Table '{table_name}' does not exist")

        if os.path.exists(schema_file):
            os.remove(schema_file)
        if os.path.exists(data_file):
            os.remove(data_file)

        index_pattern = f"{self.DATA_FOLDER}/{self.data_dir}/{table_name}_*_*.dat"
        for index_file in glob.glob(index_pattern):
            os.remove(index_file)
            
    # indexing

    def set_index(self, table: str, column: str, index_type: IndexType) -> None:

        schema_file = self._get_schema_path(table)
        data_file = self._get_data_path(table)

        if not os.path.exists(schema_file) or not os.path.exists(data_file):
            raise FileNotFoundError(
                f"Table {table} not found, cannot create index.")

        with open(schema_file, "rb") as f:
            schema = self.serializer.deserialize_schema(f.read())

        with open(data_file, "rb") as f:
            rows_data = self.serializer.deserialize_with_blocks(
                f.read(), schema["columns"])

        indexer = None
        if index_type.lower() == "hash":
            indexer = HashIndex()
            index_filename = self._get_index_path(table, column, "hash")
        elif index_type.lower() == "b+ tree":
            indexer = BPlusTreeIndex()
            index_filename = self._get_index_path(table, column, "btree")
        else:
            return

        for i, row in enumerate(rows_data):
            val = row.get(column)
            if val is not None:
                indexer.insert(val, i)

        indexer.save(index_filename)

    # statistik

    def get_stats(self, table: str) -> Statistic:

        data_file = self._get_data_path(table)
        schema_file = self._get_schema_path(table)

        with open(schema_file, "rb") as f:
            schema = f.read()

        schema_dict = self.serializer.deserialize_schema(schema)

        # l_r - ukuran tuple
        tuple_size = sum(
            col.get("length", 4) if col["type"] in ["varchar", "char"] else 4
            for col in schema_dict["columns"]
        )

        # f_r - blocking factor
        blocking_factor = self.BLOCK_SIZE // tuple_size

        with open(data_file, "rb") as f:
            data = f.read()
        data_rows = self.serializer.deserialize_with_blocks(
            data, schema_dict["columns"])

        # n_r - banyak tuple
        n_tuples = len(data_rows)

        # b_r - banyak blok
        n_blocks = ceil(n_tuples / blocking_factor)

        # V_a_r - values distinct per atribut
        distinct_val = {}
        for col in schema_dict["columns"]:
            col_name = col["name"]
            distinct_val[col_name] = len(
                set(row[col_name] for row in data_rows))

        return Statistic(n_tuples, n_blocks, tuple_size, blocking_factor, distinct_val)

    # schema read/write, data read/write

    def write_schema_file(self, schema: dict) -> None:

        table_name = schema["table_name"]
        schema_file = self._get_schema_path(table_name)

        os.makedirs(os.path.dirname(schema_file), exist_ok=True)

        schema_bytes = self.serializer.serialize_schema(schema)
        with open(schema_file, "wb") as f:
            f.write(schema_bytes)

    def write_data_file(self, table: str, data: list, schema: dict) -> None:

        data_file = self._get_data_path(table)

        os.makedirs(os.path.dirname(data_file), exist_ok=True)

        data_bytes = self.serializer.serialize_with_blocks(data, schema)
        with open(data_file, "wb") as f:
            f.write(data_bytes)

    # tektokan sama FRM, buffer

    def save_buffer_to_disk(self, buffer) -> None:
        """
        Merge buffer data back into disk, updating only modified rows.
        """
        for table in buffer.tables:
            table_name = table.name

            schema_path = self._get_schema_path(table_name)
            data_path = self._get_data_path(table_name)

            with open(schema_path, "rb") as f:
                schema_bin = f.read()
            schema = self.serializer.deserialize_schema(schema_bin)

            with open(data_path, "rb") as f:
                existing_data_bin = f.read()
            existing_rows = self.serializer.deserialize_with_blocks(
                existing_data_bin, schema["columns"])

            pk_columns = [col["name"] for col in schema["columns"]
                          if col.get("primary_key", False)]
            if not pk_columns:
                pk_columns = [schema["columns"][0]["name"]]

            buffer_rows_map = {}
            for row in table.data:
                pk_tuple = tuple(row.get(pk_col) for pk_col in pk_columns)
                buffer_rows_map[pk_tuple] = row

            # merge buffer dengan disk atau tulis ulang
            merged_rows = []
            for existing_row in existing_rows:
                pk_tuple = tuple(existing_row.get(pk_col)
                                 for pk_col in pk_columns)
                if pk_tuple in buffer_rows_map:
                    merged_rows.append(buffer_rows_map[pk_tuple])
                    del buffer_rows_map[pk_tuple]
                else:
                    merged_rows.append(existing_row)

            for remaining_row in buffer_rows_map.values():
                merged_rows.append(remaining_row)

            binary_data = self.serializer.serialize_with_blocks(
                merged_rows, schema)
            with open(data_path, "wb") as f:
                f.write(binary_data)

        buffer.tables.clear()

    def read_disk_to_buffer(self, table_name: str) -> Any:

        schema_path = self._get_schema_path(table_name)
        data_path = self._get_data_path(table_name)

        with open(schema_path, "rb") as f:
            schema_bin = f.read()
        schema = self.serializer.deserialize_schema(schema_bin)
        columns = schema["columns"]

        with open(data_path, "rb") as f:
            data_bin = f.read()

        rows = self.serializer.deserialize_with_blocks(data_bin, columns)

        return Table(table_name, rows)

    # utils

    def _get_schema_path(self, table: str) -> str:
        return f"{self.DATA_FOLDER}/{self.data_dir}/{table}_schema.dat"

    def _get_data_path(self, table: str) -> str:
        return f"{self.DATA_FOLDER}/{self.data_dir}/{table}.dat"

    def _get_index_path(self, table: str, column: str, index_type: str) -> str:
        return f"{self.DATA_FOLDER}/{self.data_dir}/{table}_{column}_{index_type}.dat"

    def _coerce_type(self, value: Any, expected_type: Optional[type], col_type_name: str) -> Any:
        if expected_type is None:
            return value
        if isinstance(value, expected_type):
            return value
        if expected_type == float and isinstance(value, int):
            return float(value)
        raise ValueError(
            f"Type mismatch: expected {col_type_name}, got {type(value).__name__}"
        )

    def _matches_conditions(self, row: dict, conditions: List) -> bool:

        if not conditions:
            return True

        for condition in conditions:
            column_value = self._get_case_insensitive(row, condition.column)

            if column_value is None:
                return False
            if not self._evaluate_condition(column_value, condition):
                return False
        return True

    def _evaluate_condition(self, value: Union[str, int], condition) -> bool:

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

        return False

    def _extract_search_value(self, conditions: Optional[List], target_col: str) -> Any:

        if not conditions:
            return None
        target_col_lower = target_col.lower() if isinstance(
            target_col, str) else target_col
        for cond in conditions:
            cond_col_lower = cond.column.lower() if isinstance(
                cond.column, str) else cond.column
            if cond_col_lower == target_col_lower and cond.operation == "=":
                return cond.operand
        return None

    def _evaluate_expression(self, expr_list: list, row: dict) -> Union[int, float]:

        # Examples:
        #    ['GPA', '*', 1.1] -> GPA * 1.1
        #    [1.05, '*', 'GPA', '+', 1] -> (1.05 * GPA) + 1

        if not expr_list:
            raise ValueError("Empty expression")

        # ganti nama kolom dengan nilai dari row
        resolved = []
        for item in expr_list:
            if isinstance(item, str) and item not in ['+', '-', '*', '/']:

                # nama kolom, ambil nilainya dari row (case-insensitive)
                val = self._get_case_insensitive(row, item, value_only=True)
                if val is None:
                    raise ValueError(f"Column '{item}' not found in row")
                try:
                    resolved.append(float(val))
                except (ValueError, TypeError):
                    raise ValueError(
                        f"Cannot convert column '{item}' value '{val}' to numeric")
            elif isinstance(item, str):
                # operator
                resolved.append(item)
            else:
                # literal numeric value
                try:
                    resolved.append(float(item))
                except (ValueError, TypeError):
                    raise ValueError(
                        f"Cannot convert '{item}' to numeric value")

        # evaluasi ekspresi dengan memperhatikan prioritas operator

        # 1st pass: handle * and /
        i = 1
        while i < len(resolved) - 1:
            if resolved[i] in ['*', '/']:
                left = resolved[i - 1]
                op = resolved[i]
                right = resolved[i + 1]

                if op == '*':
                    result = left * right
                else:  # op == '/'
                    if right == 0:
                        raise ValueError("Division by zero")
                    result = left / right

                # ganti [left, op, right] dengan result
                resolved = resolved[:i-1] + [result] + resolved[i+2:]
                # jangan increment i, cek posisi yang sama lagi
            else:
                i += 2  # skip ke posisi operator berikutnya

        # 2nd pass: handle + and -
        i = 1
        while i < len(resolved) - 1:
            if resolved[i] in ['+', '-']:
                left = resolved[i - 1]
                op = resolved[i]
                right = resolved[i + 1]

                if op == '+':
                    result = left + right
                else:  # op == '-'
                    result = left - right

                # ganti [left, op, right] dengan result
                resolved = resolved[:i-1] + [result] + resolved[i+2:]
                # jangan increment i, cek posisi yang sama lagi
            else:
                i += 2  # skip ke posisi operator berikutnya

        # pastikan cuma ada 1 hasil akhir
        if len(resolved) != 1:
            raise ValueError(f"Invalid expression: {expr_list}")

        return resolved[0]

    def _get_case_insensitive(self, row: dict, column: str, value_only: bool = True):
        """Case-insensitive column lookup. Returns value by default, or key if value_only=False"""
        column_lower = column.lower()
        for k, v in row.items():
            if k.lower() == column_lower:
                return v if value_only else k
        return None
    
    def _update_indexes(self, table: str, operation: str, row_idx: int = None, row: dict = None,
                        modified_columns: set = None, old_values: dict = None, deleted_indices: list = None) -> None:

        if operation == "insert":
            for col in modified_columns:
                val = self._get_case_insensitive(row, col)
                if val is None:
                    continue

                hash_file = self._get_index_path(table, col, "hash")
                if os.path.exists(hash_file):
                    idx = HashIndex()
                    idx.load(hash_file)
                    idx.insert(str(val), row_idx)
                    idx.save(hash_file)

                btree_file = self._get_index_path(table, col, "btree")
                if os.path.exists(btree_file):
                    idx = BPlusTreeIndex.load(btree_file)
                    idx.insert(val, row_idx)
                    idx.save(btree_file)

        elif operation == "update":
            for col in modified_columns:
                old_val = old_values.get(col)
                new_val = self._get_case_insensitive(row, col)

                if old_val == new_val:
                    continue

                if old_val is not None:
                    hash_file = self._get_index_path(table, col, "hash")
                    if os.path.exists(hash_file):
                        idx = HashIndex()
                        idx.load(hash_file)
                        idx.delete(str(old_val), row_idx)
                        idx.save(hash_file)

                    btree_file = self._get_index_path(table, col, "btree")
                    if os.path.exists(btree_file):
                        idx = BPlusTreeIndex.load(btree_file)
                        idx.delete(str(old_val), row_idx)
                        idx.save(btree_file)

                if new_val is not None:
                    hash_file = self._get_index_path(table, col, "hash")
                    if os.path.exists(hash_file):
                        idx = HashIndex()
                        idx.load(hash_file)
                        idx.insert(str(new_val), row_idx)
                        idx.save(hash_file)

                    btree_file = self._get_index_path(table, col, "btree")
                    if os.path.exists(btree_file):
                        idx = BPlusTreeIndex.load(btree_file)
                        idx.insert(str(new_val), row_idx)
                        idx.save(btree_file)

        elif operation == "delete":
            if not deleted_indices:
                return

            index_pattern = f"{self.DATA_FOLDER}/{self.data_dir}/{table}_*_*.dat"
            for index_file in glob.glob(index_pattern):
                basename = os.path.basename(index_file)
                parts = basename.replace(".dat", "").split("_")
                if len(parts) < 3:
                    continue

                col_name = parts[1]
                index_type = parts[2]

                if index_type == "hash":
                    idx = HashIndex()
                    idx.load(index_file)
                    for idx_num, row_data in deleted_indices:
                        val = row_data.get(col_name)
                        if val is not None:
                            idx.delete(str(val), idx_num)
                    idx.save(index_file)

                elif index_type == "btree":
                    idx = BPlusTreeIndex.load(index_file)
                    for idx_num, row_data in deleted_indices:
                        val = row_data.get(col_name)
                        if val is not None:
                            idx.delete(str(val), idx_num)
                    idx.save(index_file)