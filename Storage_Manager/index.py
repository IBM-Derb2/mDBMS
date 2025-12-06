class Index:
    def __init__(self) -> None:
        pass

    def serialize_hash_index(self, index_dict: dict) -> bytes:
        """
        serialisasi hash index menjadi data biner.

        Args:
            index_dict (dict): Dictionary yang memetakan key ke list indeks baris.
            contoh:
            {
                "key1": [0, 2, 5],
                "key2": [1, 3]
            }

        Returns:
            bytes: Data biner yang mewakili hash index.
        """
        binary_data = bytearray()

        # jumlah key
        binary_data.extend(len(index_dict).to_bytes(4, byteorder='big'))

        for key, values in index_dict.items():
            # panjang key
            key_bytes = str(key).encode('utf-8')
            binary_data.extend(len(key_bytes).to_bytes(4, byteorder='big'))
            # key string
            binary_data.extend(key_bytes)

            # jumlah values
            binary_data.extend(len(values).to_bytes(4, byteorder='big'))

            # values (indeks baris)
            for value in values:
                binary_data.extend(int(value).to_bytes(4, byteorder='big'))

        return bytes(binary_data)

    def deserialize_hash_index(self, binary_data: bytes) -> dict:
        """
        deserialisasi data biner menjadi hash index.

        Args:
            binary_data (bytes): Data biner yang mewakili hash index.

        Returns:
            dict: Dictionary yang memetakan key ke list indeks baris.
        """
        index_dict = {}
        i = 0

        # jumlah key
        num_keys = int.from_bytes(binary_data[i:i+4], byteorder='big')
        i += 4

        for _ in range(num_keys):
            # panjang key
            key_length = int.from_bytes(binary_data[i:i+4], byteorder='big')
            i += 4

            # key string
            key = binary_data[i:i+key_length].decode('utf-8')
            i += key_length

            # jumlah values
            num_values = int.from_bytes(binary_data[i:i+4], byteorder='big')
            i += 4

            # values (indeks baris)
            values = []
            for _ in range(num_values):
                value = int.from_bytes(binary_data[i:i+4], byteorder='big')
                i += 4
                values.append(value)

            index_dict[key] = values

        return index_dict

    def serialize_bplus_tree_node(self, node) -> bytes:
        """
        serialisasi node B+ tree menjadi data biner.

        Args:
            node: BPlusTreeNode object

        Returns:
            bytes: Data biner yang mewakili node B+ tree.
        """
        binary_data = bytearray()

        # order
        binary_data.extend(node.order.to_bytes(4, byteorder='big'))

        # is leaf (1 byte: 1 untuk leaf, 0 untuk internal)
        binary_data.append(1 if node.leaf else 0)

        # jumlah keys
        binary_data.extend(len(node.keys).to_bytes(4, byteorder='big'))

        # keys (string dengan panjang prefix)
        for key in node.keys:
            key_bytes = str(key).encode('utf-8')
            binary_data.extend(len(key_bytes).to_bytes(4, byteorder='big'))
            binary_data.extend(key_bytes)

        # jumlah children
        binary_data.extend(len(node.children).to_bytes(4, byteorder='big'))

        # children
        if node.leaf:
            # untuk leaf node, children adalah integer (indeks baris)
            for child in node.children:
                binary_data.extend(int(child).to_bytes(4, byteorder='big'))
        else:
            # untuk internal node, children adalah node lain (serialisasi rekursif)
            for child in node.children:
                child_bytes = self.serialize_bplus_tree_node(child)
                binary_data.extend(len(child_bytes).to_bytes(4, byteorder='big'))
                binary_data.extend(child_bytes)

        return bytes(binary_data)

    def deserialize_bplus_tree_node(self, binary_data: bytes, offset: int = 0):
        """
        deserialisasi data biner menjadi node B+ tree.

        Args:
            binary_data (bytes): Data biner yang mewakili node B+ tree.
            offset (int): Posisi awal membaca data.

        Returns:
            tuple: (BPlusTreeNode, offset_baru)
        """
        # import di sini untuk menghindari circular dependency
        from .b_plus_tree_index import BPlusTreeNode

        # order
        order = int.from_bytes(binary_data[offset:offset+4], byteorder='big')
        offset += 4

        # is_leaf
        is_leaf = binary_data[offset] == 1
        offset += 1

        # buat node
        node = BPlusTreeNode(order, leaf=is_leaf)

        # jumlah keys
        num_keys = int.from_bytes(binary_data[offset:offset+4], byteorder='big')
        offset += 4

        # keys
        for _ in range(num_keys):
            key_length = int.from_bytes(binary_data[offset:offset+4], byteorder='big')
            offset += 4
            key = binary_data[offset:offset+key_length].decode('utf-8')
            offset += key_length
            node.keys.append(key)

        # jumlah children
        num_children = int.from_bytes(binary_data[offset:offset+4], byteorder='big')
        offset += 4

        # children
        if is_leaf:
            # untuk leaf node, children adalah integer
            for _ in range(num_children):
                child = int.from_bytes(binary_data[offset:offset+4], byteorder='big')
                offset += 4
                node.children.append(child)
        else:
            # untuk internal node, children adalah node
            for _ in range(num_children):
                child_length = int.from_bytes(binary_data[offset:offset+4], byteorder='big')
                offset += 4
                child_node, offset = self.deserialize_bplus_tree_node(binary_data, offset)
                node.children.append(child_node)

        return node, offset

    def serialize_bplus_tree(self, root_node) -> bytes:
        """
        serialisasi B+ tree (root node) menjadi data biner.

        Args:
            root_node: Root BPlusTreeNode

        Returns:
            bytes: Data biner yang mewakili B+ tree.
        """
        return self.serialize_bplus_tree_node(root_node)

    def deserialize_bplus_tree(self, binary_data: bytes):
        """
        deserialisasi data biner menjadi B+ tree (root node).

        Args:
            binary_data (bytes): Data biner yang mewakili B+ tree.

        Returns:
            BPlusTreeNode: Root node dari B+ tree.
        """
        node, _ = self.deserialize_bplus_tree_node(binary_data, 0)
        return node
