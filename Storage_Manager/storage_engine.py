from __future__ import annotations
from typing import Union, List, Any, Optional
from math import ceil
import os
import glob

from globalsy.classes.rows import Rows
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

        # if possible, use index scan
        candidate_indices = self._get_candidate_indices(
            data_retrieval, table, schema_dict)

        # if buffer has dirty data for this table (optimization)
        has_dirty_buffer = any(
            buffered_row.table_name == table
            for buffered_row in self.frm.buffer_manager.buffer_data.values()
        )

        # read rows from disk
        disk_rows = self._read_disk_rows(
            data_file, schema_dict, candidate_indices)

        # merge with buffer if needed
        if has_dirty_buffer:
            rows = self._merge_buffer_with_disk(disk_rows, table, schema_dict)
        else:
            rows = disk_rows

        # apply conditions and projection
        return self._apply_query_filters(rows, table, data_retrieval)

    def _get_candidate_indices(self, data_retrieval: DataRetrieval, table: str, schema_dict: dict) -> Optional[List[int]]:

        if data_retrieval.search_type != "index" or data_retrieval.index_column is None:
            return None

        target_col = data_retrieval.index_column
        
        # equality search first (=)
        search_value = self._extract_search_value(data_retrieval.conditions, target_col)
        if search_value is not None:
            hash_index_file = self._get_index_path(table, target_col, "hash")
            if os.path.exists(hash_index_file):
                return self._scan_using_hash_index(hash_index_file, search_value)

            btree_index_file = self._get_index_path(table, target_col, "btree")
            if os.path.exists(btree_index_file):
                return self._scan_using_btree_index(btree_index_file, equality=search_value)
        
        # range search (>, <, >=, <=), only B+ tree supports this
        range_bounds = self._extract_range_bounds(data_retrieval.conditions, target_col)
        if range_bounds is not None:
            btree_index_file = self._get_index_path(table, target_col, "btree")
            if os.path.exists(btree_index_file):
                return self._scan_using_btree_index(btree_index_file, range_bounds=range_bounds)

        return None

    def _read_disk_rows(self, data_file: str, schema_dict: dict, candidate_indices: Optional[List[int]]) -> List[dict]:

        if candidate_indices is not None:
            # index-based random access read
            row_size = self.serializer.get_row_size(schema_dict["columns"])
            rows_per_block = self.BLOCK_SIZE // row_size
            disk_rows = []

            with open(data_file, "rb") as f:
                for idx in candidate_indices:
                    block_idx = idx // rows_per_block
                    inner_idx = idx % rows_per_block
                    byte_offset = (block_idx * self.BLOCK_SIZE) + (inner_idx * row_size)

                    f.seek(byte_offset)
                    row_binary = f.read(row_size)

                    if not row_binary:
                        continue

                    row = self.serializer.deserialize_single_row(
                        row_binary, schema_dict["columns"])
                    disk_rows.append(row)
        else:
            # full table scan
            with open(data_file, "rb") as f:
                binary_data = f.read()
            disk_rows = self.serializer.deserialize_with_blocks(
                binary_data, schema_dict["columns"])

        return disk_rows

    def _merge_buffer_with_disk(self, disk_rows: List[dict], table: str, schema_dict: dict) -> List[dict]:

        pk_columns = [col["name"]
                      for col in schema_dict["columns"] if col.get("primary_key")]
        if not pk_columns:
            pk_columns = [schema_dict["columns"][0]["name"]]

        buffered_rows_map = {}
        deleted_pk_tuples = set()

        for key, buffered_row in self.frm.buffer_manager.buffer_data.items():
            if buffered_row.table_name == table:
                pk_tuple = tuple(sorted(buffered_row.primary_key_value.items()))
                if buffered_row.is_deleted:
                    deleted_pk_tuples.add(pk_tuple)
                else:
                    buffered_rows_map[pk_tuple] = buffered_row.data

        merged_rows = []
        processed_buffer_keys = set()

        for disk_row in disk_rows:
            pk_value = {pk_col: disk_row[pk_col] for pk_col in pk_columns}
            pk_tuple = tuple(sorted(pk_value.items()))

            if pk_tuple in deleted_pk_tuples:
                continue  # skip deleted rows
            elif pk_tuple in buffered_rows_map:
                merged_rows.append(buffered_rows_map[pk_tuple])
                processed_buffer_keys.add(pk_tuple)
            else:
                merged_rows.append(disk_row)

        # add buffer-only rows (new inserts not yet on disk)
        for pk_tuple, buffered_data in buffered_rows_map.items():
            if pk_tuple not in processed_buffer_keys:
                merged_rows.append(buffered_data)

        return merged_rows

    def _apply_query_filters(self, rows: List[dict], table: str, data_retrieval: DataRetrieval) -> Rows:

        result_rows = Rows()
        target_columns = set(data_retrieval.column)
        wants_all_columns = "*" in target_columns or not target_columns

        for idx, row in enumerate(rows):
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
                if col["name"] == data_write.column[0]:
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
                                (c for c in schema_dict["columns"] if c["name"] == col_name), None)
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
                        (c for c in schema_dict["columns"] if c["name"] == col_name), None)
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

            # cek duplikasi di buffer (skip deleted rows)
            pk_value_dict = {pk_col: new_row.get(pk_col) for pk_col in pk_columns}
            # Check if row exists in buffer and is not deleted
            buffer_key = self.frm.buffer_manager._get_buffer_key(table, pk_value_dict)
            if buffer_key in self.frm.buffer_manager.buffer_data:
                buffered_row_obj = self.frm.buffer_manager.buffer_data[buffer_key]
                if not buffered_row_obj.is_deleted:
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

            self._update_indexes(
                table=table,
                operation="insert",
                row_idx=new_idx,
                row=new_row,
                modified_columns=set(new_row.keys())
            )

        # UPDATE (dengan conditions)
        else:
            # pk for buffer
            pk_columns = [col["name"] for col in schema_dict["columns"]
                         if col.get("primary_key", False)]
            if not pk_columns:
                pk_columns = [schema_dict["columns"][0]["name"]]

            # merge buffer dengan disk
            buffered_rows_map = {}
            deleted_pk_tuples = set()

            for key, buffered_row in self.frm.buffer_manager.buffer_data.items():
                if buffered_row.table_name == table:
                    pk_tuple = tuple(sorted(buffered_row.primary_key_value.items()))
                    if buffered_row.is_deleted:
                        deleted_pk_tuples.add(pk_tuple)
                    else:
                        buffered_rows_map[pk_tuple] = buffered_row.data

            merged_rows = []
            processed_buffer_keys = set()

            for disk_row in rows_data:
                pk_value = {pk_col: disk_row[pk_col] for pk_col in pk_columns}
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

            # Normalize new_value to always be a list
            if not isinstance(data_write.new_value, list):
                new_values = [data_write.new_value]
            else:
                new_values = data_write.new_value

            for i, row in enumerate(merged_rows):
                if self._matches_conditions(row, data_write.conditions):
                    updated_row = row.copy()
                    old_values = {}
                    modified_columns = set()
                    
                    # Process all columns and their corresponding values
                    for col_idx, target_col in enumerate(data_write.column):
                        if target_col not in row:
                            continue
                        
                        old_values[target_col] = row.get(target_col)
                        modified_columns.add(target_col)
                        
                        # Get the column type from schema
                        col_schema = next(
                            (c for c in schema_dict["columns"] if c["name"] == target_col), None)
                        if not col_schema:
                            continue
                            
                        col_type = col_schema["type"]
                        expected_type = self.TYPE_MAPPING.get(col_type)
                        
                        # Get the corresponding value
                        if col_idx < len(new_values):
                            new_val = new_values[col_idx]
                        else:
                            continue
                        
                        # Handle both expressions and literals
                        if isinstance(new_val, list):
                            # handle arithmetic expressions: ['GPA', '*', 1.1]
                            try:
                                calc_value = self._evaluate_expression(new_val, row)
                            except Exception:
                                continue
                            coerced_value = self._coerce_type(calc_value, expected_type, col_type)
                        else:
                            coerced_value = self._coerce_type(new_val, expected_type, col_type)
                        
                        updated_row[target_col] = coerced_value

                    pk_value_dict = {pk_col: updated_row.get(pk_col) for pk_col in pk_columns}
                    self.frm.buffer_manager.write_block(
                        transaction_id=transaction_id,
                        table_name=table,
                        pk_value=pk_value_dict,
                        new_data=updated_row
                    )

                    self._update_indexes(
                        table=table,
                        operation="update",
                        row_idx=i,
                        row=updated_row,
                        modified_columns=modified_columns,
                        old_values=old_values
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

        disk_rows = self.serializer.deserialize_with_blocks(
            data_binary, schema_columns)

        # Merge buffer with disk to include uncommitted inserts
        buffered_rows_map = {}
        deleted_pk_tuples = set()

        for key, buffered_row in self.frm.buffer_manager.buffer_data.items():
            if buffered_row.table_name == table_name:
                pk_tuple = tuple(sorted(buffered_row.primary_key_value.items()))
                if buffered_row.is_deleted:
                    deleted_pk_tuples.add(pk_tuple)
                else:
                    buffered_rows_map[pk_tuple] = buffered_row.data

        # Merge disk rows with buffer
        all_rows = []
        processed_buffer_keys = set()

        for disk_row in disk_rows:
            pk_value = {pk_col: disk_row[pk_col] for pk_col in pk_columns}
            pk_tuple = tuple(sorted(pk_value.items()))

            if pk_tuple in deleted_pk_tuples:
                continue  # Skip rows marked as deleted in buffer
            elif pk_tuple in buffered_rows_map:
                all_rows.append(buffered_rows_map[pk_tuple])  # Use buffer version
                processed_buffer_keys.add(pk_tuple)
            else:
                all_rows.append(disk_row)  # Use disk version

        # Add buffer-only rows (inserts not yet on disk)
        for pk_tuple, buffered_data in buffered_rows_map.items():
            if pk_tuple not in processed_buffer_keys:
                all_rows.append(buffered_data)

        if not all_rows:
            return 0

        deleted_count = 0
        has_conditions = data_deletion.conditions and len(
            data_deletion.conditions) > 0

        transaction_id = getattr(data_deletion, 'transaction_id', 0)
        deleted_indices = []

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
                deleted_indices.append((i, row))
                deleted_count += 1

        if deleted_indices:
            self._update_indexes(
                table=table_name,
                operation="delete",
                deleted_indices=deleted_indices
            )

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
                indexer.insert(self._normalize_index_key(val), i)

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
                # Normalize to lowercase for consistent comparison
                pk_tuple = tuple(row.get(pk_col.lower(), row.get(pk_col)) for pk_col in pk_columns)
                buffer_rows_map[pk_tuple] = row

            # Get deleted keys from buffer (if available)
            # deleted_keys contains tuples of PK values
            deleted_keys_set = set()
            for dk in table.deleted_keys:
                # dk is already a tuple of values
                deleted_keys_set.add(dk)

            # merge buffer dengan disk atau tulis ulang
            merged_rows = []
            for existing_row in existing_rows:
                # Normalize to lowercase for consistent comparison
                pk_tuple = tuple(existing_row.get(pk_col.lower(), existing_row.get(pk_col))
                                 for pk_col in pk_columns)
                # Skip rows that were deleted in buffer
                if pk_tuple in deleted_keys_set:
                    continue
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
            # Case-insensitive column lookup
            column_value = None
            col_lower = condition.column.lower()
            for k, v in row.items():
                if k.lower() == col_lower:
                    column_value = v
                    break

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
        for cond in conditions:
            if cond.column == target_col and cond.operation == "=":
                return cond.operand
        return None
    
    def _normalize_index_key(self, value: Any) -> str:
        """Normalize index key for consistent lexicographic ordering.
        Numbers are zero-padded: 2.5 -> '002.50', 10.3 -> '010.30'
        Strings are returned as-is.
        """
        if isinstance(value, (int, float)):
            # Format as zero-padded: width=6, 2 decimals -> '002.50'
            return f"{float(value):06.2f}"
        return str(value)
    
    def _extract_range_bounds(self, conditions: Optional[List], target_col: str) -> Optional[tuple]:

        if not conditions:
            return None
        
        min_val = None
        max_val = None
        
        for cond in conditions:
            if cond.column != target_col:
                continue
            
            if cond.operation in (">", ">="):
                min_val = self._normalize_index_key(cond.operand)
            elif cond.operation in ("<", "<="):
                max_val = self._normalize_index_key(cond.operand)
        
        # if found at least one bound
        return (min_val, max_val) if (min_val is not None or max_val is not None) else None
    
    def _scan_using_hash_index(self, index_path: str, search_key: Any) -> List[int]:
        indexer = HashIndex()
        indexer.load(index_path)
        return indexer.search(self._normalize_index_key(search_key))

    def _scan_using_btree_index(self, index_path: str, equality: Any = None, range_bounds: tuple = None) -> List[int]:
        """Scan B+ tree for exact match or range."""
        indexer = BPlusTreeIndex.load(index_path)
        
        if equality is not None:
            result = indexer.search(self._normalize_index_key(equality))
        elif range_bounds is not None:
            min_val, max_val = range_bounds
            result = indexer.search_range(min_val, max_val)
        else:
            return []
        
        return result if result else []

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

                # nama kolom, ambil nilainya dari row
                val = row.get(item)
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

    def _update_indexes(self, table: str, operation: str, row_idx: int = None, row: dict = None,
                        modified_columns: set = None, old_values: dict = None, deleted_indices: list = None) -> None:

        if operation == "insert":
            for col in modified_columns:
                val = row.get(col)
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
                    idx.insert(str(val), row_idx)
                    idx.save(btree_file)

        elif operation == "update":
            for col in modified_columns:
                old_val = old_values.get(col)
                new_val = row.get(col)

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