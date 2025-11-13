from __future__ import annotations
from typing import Union, List
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

    def _get_path(self, table: str, file_type: str = "data") -> str:
        """Helper to get file paths with DATA_FOLDER/data_dir structure"""
        if self.data_dir:
            base_path = f"{self.DATA_FOLDER}/{self.data_dir}"
        else:
            base_path = self.DATA_FOLDER

        if file_type == "schema":
            return f"{base_path}/{table}_schema.dat"
        else:  # data
            return f"{base_path}/{table}.dat"

    def read_block(self, data_retrieval: DataRetrieval) -> Rows:
        """
        Read block data from the hard disk based on the DataRetrieval object and return it in Rows format.
        Args:
            data_retrieval (DataRetrieval): Object that contains information about the table, columns, and conditions.

        Returns:
            Rows: Rows object containing the read data.
        """
        table = data_retrieval.table
        schema_file = self._get_path(table, "schema")
        data_file = self._get_path(table, "data")

        try:
            with open(schema_file, "rb") as f:
                schema = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"File schema for {table} table is not found")

        skema = self.serializer.deserialize_schema(schema)

        try:
            with open(data_file, "rb") as f:
                binary_data = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"File data table for {table} table is not found")

        rows_data = self.serializer.deserialize_with_blocks(binary_data, skema["columns"])

        if len(rows_data) == 0:
            return Rows()

        # mencari semua column yang ada di rows_data
        columns = set()
        for row in rows_data:
            columns.update(row.keys())

        # mengurangi columns dengan kolom yang ada pada data_retrieval.column
        columns = list(columns - set(data_retrieval.column))

        temp = Rows()
        for i in range(len(rows_data)):
            if self._matches_conditions(rows_data[i], data_retrieval.conditions):
                if len(data_retrieval.column) == 1 and data_retrieval.column[0] == "*":
                    temp.data.append(rows_data[i])
                    temp.idx.append(i)
                else:
                    # mengurangi rows_data[i] dengan column yang ada pada columns
                    for col in columns:
                        del rows_data[i][col]
                    temp.data.append(rows_data[i])
                    temp.idx.append(i)

        temp.rows_count = len(temp.data)
        return temp

    def _matches_conditions(self, row: dict, conditions: List) -> bool:
        """
        Checks whether a row satisfies all given conditions.

        Args:
            row (dict): Data row to be checked.
            conditions (List[Condition]): List of conditions to be satisfied.

        Returns:
            bool: True if the row satisfies all conditions, False otherwise.
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
        Evaluates whether a value satisfies a given condition.

        Args:
            value (Union[str, int]): Value to be evaluated.
            condition (Condition): Condition to be applied.

        Returns:
            bool: True if the value satisfies the condition, False otherwise.
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
        else:
            raise ValueError(f"Operation is not known: {condition.operation}")

    def write_block(self, data_write: DataWrite) -> Rows:
        """
        Write/update block data to the hard disk based on the DataWrite object.
        Args:
            data_write (DataWrite): Object that contains information about the table, columns, conditions, and also new_value.

        Returns:
            Rows: Rows object containing the updated data.
        """
        table = data_write.table
        schema_file = self._get_path(table, "schema")
        data_file = self._get_path(table, "data")

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

        # mengambil data yang akan diubah
        temp = Rows()
        for i in range(len(rows_data)):
            if isinstance(data_write.new_value, list):
                operasi = ""
                for j in data_write.new_value:
                    if isinstance(j, int):
                        operasi += str(j)
                    else:
                        if j in rows_data[i]:
                            operasi += str(rows_data[i][j])
                        else:
                            operasi += str(j)

                tempNewValue = eval(operasi)

                if (
                    self._matches_conditions(rows_data[i], data_write.conditions)
                    and isinstance(tempNewValue, int)
                    and isinstance(rows_data[i][data_write.column[0]], int)
                ):
                    rows_data[i][data_write.column[0]] = tempNewValue
                    temp.data.append(rows_data[i])
                    temp.idx.append(i)
            else:
                for j in skema["columns"]:
                    if j["name"] == data_write.column[0]:
                        tipe = j["type"]
                        break

                type_mapping = {
                    "int": int,
                    "float": float,
                    "varchar": str,
                    "char": str,
                }

                type_rill = type_mapping.get(tipe)

                if self._matches_conditions(
                    rows_data[i], data_write.conditions
                ) and isinstance(data_write.new_value, type_rill):
                    rows_data[i][data_write.column[0]] = data_write.new_value
                    temp.data.append(rows_data[i])
                    temp.idx.append(i)

        temp.rows_count = len(temp.data)

        tes = {"columns": skema["columns"]}
        binary_data = self.serializer.serialize_with_blocks(temp.data, tes)
        with open(data_file, "wb") as f:
            f.write(binary_data)

        return temp
    
    def delete_block(self, data_deletion: DataDeletion) -> int:
        """
        Delete rows from table based on conditions. Uses "Read-All, Filter, Write-All" strategy.

        Args:
            data_deletion (DataDeletion): Object that contains table name and WHERE conditions.
        Returns:
            int: Number of rows successfully deleted.
        """
        table_name = data_deletion.table
        schema_file = self._get_path(table_name, "schema")
        data_file = self._get_path(table_name, "data")

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

        # Filter
        rows_to_keep = []
        deleted_count = 0
        has_conditions = data_deletion.conditions and len(data_deletion.conditions) > 0

        for row in all_rows:
            if not has_conditions:
                # no WHERE clause -> delete all
                deleted_count += 1
            elif self._matches_conditions(row, data_deletion.conditions):
                # has WHERE and matches -> delete
                deleted_count += 1
            else:
                # has WHERE but doesn't match -> keep
                rows_to_keep.append(row)

        # Overwrite
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
        """
        table: table name to be indexed
        column: column name to be indexed
        index_type: index type to be used, either "b+ tree" or "hash"
        """
        # TODO: Load data from self._get_path

        if index_type == "b+ tree":
            indexer = BPlusTreeIndex()
            # TODO: do indexing, depends on data format
            pass
        elif index_type == "hash":
            indexer = HashIndex()
            # TODO: do indexing, depends on data format
            pass

        return None

    def get_stats(self, table: str) -> Statistic:
        """
        Get statistics for a table.

        Args:
            table (str): Table name

        Returns:
            Statistic: Statistics object containing n_r, b_r, l_r, f_r, V_a_r
        """
        block_size = 1024
        data_file = self._get_path(table, "data")
        schema_file = self._get_path(table, "schema")

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
        Write schema to file using serializer.

        Args:
            schema (dict): Schema dictionary containing table_name and columns
        """
        table_name = schema["table_name"]
        schema_file = self._get_path(table_name, "schema")

        # Create directory if doesn't exist
        import os
        os.makedirs(os.path.dirname(schema_file), exist_ok=True)

        schema_bytes = self.serializer.serialize_schema(schema)
        with open(schema_file, "wb") as f:
            f.write(schema_bytes)

    def write_data_file(self, table: str, data: list, schema: dict) -> None:
        """
        Write data to file using serializer.

        Args:
            table (str): Table name
            data (list): List of row dictionaries
            schema (dict): Schema dictionary containing columns info
        """
        data_file = self._get_path(table, "data")

        # Create directory if doesn't exist
        import os
        os.makedirs(os.path.dirname(data_file), exist_ok=True)

        data_bytes = self.serializer.serialize_with_blocks(data, schema)
        with open(data_file, "wb") as f:
            f.write(data_bytes)
