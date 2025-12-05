from collections import defaultdict
import pickle
import os
import sys

if __name__ == "__main__":
    from serializer import Serializer
else:
    from .serializer import Serializer

class HashIndex:
    def __init__(self):
        self.index = defaultdict(list)

    def insert(self, key: str, value: int):
        self.index[key].append(value)
    
    def delete(self, key: str, value: int):
        if key in self.index and value in self.index[key]:
            self.index[key].remove(value)
            if not self.index[key]:
                del self.index[key]

    def search(self, key: str) -> list[int]:
        return self.index.get(key, [])

    def save(self, filepath: str):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            pickle.dump(self.index, f)

    def load(self, filepath: str):
        if not os.path.exists(filepath):
            self.index = defaultdict(list)
            return
        with open(filepath, 'rb') as f:
            self.index = pickle.load(f)

    @staticmethod
    def _get_original_column_name(schema: dict, column: str) -> str:
        for col in schema['columns']:
            if col['name'].lower() == column.lower():
                return col['name']
        return None

    @staticmethod
    def create(table: str, column: str, data_dir: str = "data"):
        serializer = Serializer()

        schema_file = os.path.join(data_dir, f"{table}_schema.dat")
        data_file = os.path.join(data_dir, f"{table}.dat")
        
        hash_index_file = os.path.join(data_dir, f"{table}_{column}_hash.dat")
        btree_index_file = os.path.join(data_dir, f"{table}_{column}_btree.dat")
        index_file = hash_index_file
        
        if os.path.exists(hash_index_file):
            raise FileExistsError(f"Hash index already exists for {table}.{column}")
        if os.path.exists(btree_index_file):
            raise FileExistsError(f"B+ tree index already exists for {table}.{column}")

        if not os.path.exists(schema_file):
            raise FileNotFoundError(f"Table '{table}' does not exist (schema file not found)")

        if not os.path.exists(data_file):
            raise FileNotFoundError(f"Table '{table}' does not exist (data file not found)")

        with open(schema_file, 'rb') as f:
            schema = serializer.deserialize_schema(f.read())

        original_col_name = HashIndex._get_original_column_name(schema, column)
        if original_col_name is None:
            columns = [col['name'] for col in schema['columns']]
            raise ValueError(f"Column '{column}' does not exist in table '{table}'. Available columns: {', '.join(columns)}")

        hash_index = HashIndex()

        with open(data_file, 'rb') as f:
            data = f.read()

        rows = serializer.deserialize_with_blocks(data, schema['columns'])

        for idx, row in enumerate(rows):
            key_value = str(row.get(original_col_name, ''))
            hash_index.insert(key_value, idx)

        hash_index.save(index_file)
        return index_file

    @staticmethod
    def drop(table: str, column: str, data_dir: str = "data"):
        index_file = os.path.join(data_dir, f"{table}_{column}_hash.dat")

        if not os.path.exists(index_file):
            raise FileNotFoundError(f"Hash index does not exist for {table}.{column}")

        os.remove(index_file)


def main():
    if len(sys.argv) < 4:
        print("Usage: python hash_index.py <create|drop> <column> <table>")
        sys.exit(1)

    action = sys.argv[1].lower()
    column = sys.argv[2]
    table = sys.argv[3]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(os.path.dirname(script_dir), "data")

    try:
        if action == "create":
            print(f"Creating hash index for {table}.{column}...")
            index_file = HashIndex.create(table, column, data_dir)

            serializer = Serializer()
            schema_file = os.path.join(data_dir, f"{table}_schema.dat")
            data_file = os.path.join(data_dir, f"{table}.dat")
            with open(schema_file, 'rb') as f:
                schema = serializer.deserialize_schema(f.read())
            with open(data_file, 'rb') as f:
                rows = serializer.deserialize_with_blocks(f.read(), schema['columns'])

            print(f"Hash index created successfully at {index_file}")
            print(f"Indexed {len(rows)} rows")

        elif action == "drop":
            HashIndex.drop(table, column, data_dir)
            print(f"Hash index dropped successfully for {table}.{column}")

        else:
            print(f"Error: Unknown action '{action}'. Use 'create' or 'drop'")
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        serializer = Serializer()
        schema_file = os.path.join(data_dir, f"{table}_schema.dat")
        with open(schema_file, 'rb') as f:
            schema = serializer.deserialize_schema(f.read())
            columns = [col['name'].lower() for col in schema['columns']]
        print(f"Available columns: {', '.join(columns)}")
        sys.exit(1)
    except FileExistsError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()