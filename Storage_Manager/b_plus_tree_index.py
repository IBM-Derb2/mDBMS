from typing import Union
import pickle
import os
import sys

if __name__ == "__main__":
    from serializer import Serializer
else:
    from .serializer import Serializer

class BPlusTreeNode:
    def __init__(self, order, leaf=False):
        self.order = order
        self.leaf = leaf
        self.keys = []
        self.children = []
        self.next = None

    def __getstate__(self):
        state = self.__dict__.copy()
        state["next"] = None
        return state

class BPlusTreeIndex:
    def __init__(self, order=5):
        self.root = BPlusTreeNode(order, leaf=True)
        self.order = order
    
    def search(self, key):
        leaf = self._find_leaf(self.root, key)
        if not leaf or not leaf.keys:
            return None
        
        results = []
        
        key_exists = any(k == key for k in leaf.keys)
        if not key_exists:
            return None
        
        start_leaf = self.root
        while not start_leaf.leaf:
            inserted = False
            for i, k in enumerate(start_leaf.keys):
                if key <= k:
                    start_leaf = start_leaf.children[i]
                    inserted = True
                    break
            if not inserted:
                start_leaf = start_leaf.children[-1]
        
        current_leaf = start_leaf
        while current_leaf:
            for i, k in enumerate(current_leaf.keys):
                if k == key:
                    results.append(current_leaf.children[i])
                elif k > key:
                    return results if results else None
            current_leaf = current_leaf.next
        
        return results if results else None

    def search_range(self, start_key, end_key): 
        results = []
        leaf = self._find_leaf(self.root, start_key)

        while leaf:
            for k, v in zip(leaf.keys, leaf.children):
                if start_key <= k <= end_key:
                    results.append((k, v))
                if k > end_key:
                    return results
            leaf = leaf.next

        return results


    def insert(self, key: str, value: int) -> None:
        node = self._find_leaf(self.root, key)
        
        index = 0
        while index < len(node.keys) and node.keys[index] < key:
            index += 1

        node.keys.insert(index, key)
        node.children.insert(index, value)

        if len(node.keys) > self.order - 1:
            self._split_leaf(node)
    
    def delete(self, key: str, value: int) -> None:
        leaf = self._find_leaf(self.root, key)
        if not leaf:
            return

        for i, (k, v) in enumerate(zip(leaf.keys, leaf.children)):
            if k == key and v == value:
                leaf.keys.pop(i)
                leaf.children.pop(i)
                break

    def save(self, filename):
        with open(filename, "wb") as f:
            pickle.dump(self.root, f)

    def _rebuild_leaf_links(self, node=None):
        if node is None:
            node = self.root
        
        if node.leaf:
            return [node]
        
        all_leaves = []
        for child in node.children:
            all_leaves.extend(self._rebuild_leaf_links(child))
        
        for i in range(len(all_leaves) - 1):
            all_leaves[i].next = all_leaves[i + 1]
        
        return all_leaves

    @staticmethod
    def load(filename):
        with open(filename, "rb") as f:
            tree = BPlusTreeIndex()
            tree.root = pickle.load(f)
            tree._rebuild_leaf_links()
            return tree

    @staticmethod
    def _get_original_column_name(schema: dict, column: str) -> str:
        for col in schema['columns']:
            if col['name'].lower() == column.lower():
                return col['name']
        return None

    @staticmethod
    def create(table: str, column: str, data_dir: str = "data", order: int = 5):
        serializer = Serializer()

        schema_file = os.path.join(data_dir, f"{table}_schema.dat")
        data_file = os.path.join(data_dir, f"{table}.dat")
        
        hash_index_file = os.path.join(data_dir, f"{table}_{column}_hash.dat")
        btree_index_file = os.path.join(data_dir, f"{table}_{column}_btree.dat")
        index_file = btree_index_file

        if not os.path.exists(schema_file):
            raise FileNotFoundError(f"Table '{table}' does not exist (schema file not found)")

        if not os.path.exists(data_file):
            raise FileNotFoundError(f"Table '{table}' does not exist (data file not found)")

        with open(schema_file, 'rb') as f:
            schema = serializer.deserialize_schema(f.read())

        if os.path.exists(hash_index_file):
            raise FileExistsError(f"Hash index already exists for {table}.{column}")
        if os.path.exists(btree_index_file):
            raise FileExistsError(f"B+ tree index already exists for {table}.{column}")

        original_col_name = BPlusTreeIndex._get_original_column_name(schema, column)
        if original_col_name is None:
            columns = [col['name'] for col in schema['columns']]
            raise ValueError(f"Column '{column}' does not exist in table '{table}'. Available columns: {', '.join(columns)}")

        btree_index = BPlusTreeIndex(order=order)

        with open(data_file, 'rb') as f:
            data = f.read()

        rows = serializer.deserialize_with_blocks(data, schema['columns'])

        for idx, row in enumerate(rows):
            key_value = str(row.get(original_col_name, ''))
            btree_index.insert(key_value, idx)

        btree_index.save(index_file)
        return index_file

    @staticmethod
    def drop(table: str, column: str, data_dir: str = "data"):
        index_file = os.path.join(data_dir, f"{table}_{column}_btree.dat")

        if not os.path.exists(index_file):
            raise FileNotFoundError(f"B+ tree index does not exist for {table}.{column}")

        os.remove(index_file)

    def _find_leaf(self, node, key) -> Union[BPlusTreeNode]: 
        if node.leaf:
            return node
        for i, item in enumerate(node.keys):
            if key < item:
                return self._find_leaf(node.children[i], key)
            
        return self._find_leaf(node.children[-1], key)
    
    def _split_leaf(self, node) -> None:
        mid = len(node.keys) // 2

        new_leaf = BPlusTreeNode(self.order, leaf=True)
        new_leaf.keys = node.keys[mid:]
        new_leaf.children = node.children[mid:]
        node.keys = node.keys[:mid]
        node.children = node.children[:mid]

        new_leaf.next = node.next
        node.next = new_leaf

        if node == self.root:
            new_root = BPlusTreeNode(self.order)
            new_root.keys = [new_leaf.keys[0]]
            new_root.children = [node, new_leaf]
            self.root = new_root
        else:
            self._insert_into_parent(node, new_leaf.keys[0], new_leaf)

    def _insert_into_parent(self, node, key, new_node) -> None:
        parent = self._find_parent(self.root, node)
        if not parent:
            new_root = BPlusTreeNode(self.order)
            new_root.keys = [key]
            new_root.children = [node, new_node]
            self.root = new_root
            return

        idx = parent.children.index(node)
        parent.keys.insert(idx, key)
        parent.children.insert(idx + 1, new_node)

        if len(parent.keys) > self.order - 1:
            self._split_internal(parent)
    
    def _split_internal(self, node) -> None:
        mid = len(node.keys) // 2
        up_key = node.keys[mid]

        new_internal = BPlusTreeNode(self.order)
        new_internal.keys = node.keys[mid + 1:]
        new_internal.children = node.children[mid + 1:]
        
        node.keys = node.keys[:mid]
        node.children = node.children[:mid + 1]

        if node == self.root:
            new_root = BPlusTreeNode(self.order)
            new_root.keys = [up_key]
            new_root.children = [node, new_internal]
            self.root = new_root
        else:
            self._insert_into_parent(node, up_key, new_internal)

    def _find_parent(self, current, child) -> Union[BPlusTreeNode, None]:
        if current.leaf:
            return None
        for c in current.children:
            if c == child:
                return current
            if not c.leaf:
                parent = self._find_parent(c, child)
                if parent:
                    return parent

        return None


def main():
    if len(sys.argv) < 4:
        print("Usage: python b_plus_tree_index.py <create|drop> <column> <table>")
        sys.exit(1)

    action = sys.argv[1].lower()
    column = sys.argv[2]
    table = sys.argv[3]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(os.path.dirname(script_dir), "data")

    try:
        if action == "create":
            print(f"Creating B+ tree index for {table}.{column}...")
            index_file = BPlusTreeIndex.create(table, column, data_dir, order=5)

            serializer = Serializer()
            schema_file = os.path.join(data_dir, f"{table}_schema.dat")
            data_file = os.path.join(data_dir, f"{table}.dat")
            with open(schema_file, 'rb') as f:
                schema = serializer.deserialize_schema(f.read())
            with open(data_file, 'rb') as f:
                rows = serializer.deserialize_with_blocks(f.read(), schema['columns'])

            print(f"B+ tree index created successfully at {index_file}")
            print(f"Indexed {len(rows)} rows")

        elif action == "drop":
            BPlusTreeIndex.drop(table, column, data_dir)
            print(f"B+ tree index dropped successfully for {table}.{column}")

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