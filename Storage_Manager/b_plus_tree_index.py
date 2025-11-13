class BPlusTreeNode:
    def __init__(self, order, leaf=False):
        self.order = order
        self.leaf = leaf
        self.keys = []
        self.children = []

class BPlusTreeIndex: 
    def __init__(self, order=5):
        self.root = BPlusTreeNode(order, leaf=True)
        self.order = order
    
    def search(self, key): # TODO: implement
        pass

    def search_range(self, start_key, end_key): # TODO: implement
        pass

    def insert(self, key: str, value: int):
        node = self._find_leaf(self.root, key)
        insert_pos = 0

        while insert_pos < len(node.keys) and node.keys[insert_pos] < key:
            insert_pos += 1
        node.keys.insert(insert_pos, key)
        node.children.insert(insert_pos, value)

        if len(node.keys) > self.order - 1:
            self._split_leaf(node)

    def _find_leaf(self, node, key):
        if node.leaf:
            return node
        for i, item in enumerate(node.keys):
            if key < item:
                return self._find_leaf(node.children[i], key)
            
        return self._find_leaf(node.children[-1], key)
    
    def _split_leaf(self, node):
        mid = len(node.keys) // 2
        new_leaf = BPlusTreeNode(self.order, leaf=True)
        new_leaf.keys = node.keys[mid:]
        new_leaf.children = node.children[mid:]

        node.keys = node.keys[:mid]
        node.children = node.children[:mid]

        new_leaf.children.append(node.children[-1] if len(node.children) > len(node.keys) else None)
        node.children[-1] = new_leaf

        if node == self.root:
            new_root = BPlusTreeNode(self.order)
            new_root.keys = [new_leaf.keys[0]]
            new_root.children = [node, new_leaf]
            self.root = new_root
        else:
            self._insert_into_parent(node, new_leaf.keys[0], new_leaf)

    def _insert_into_parent(self, node, key, new_node):
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
    
    def _split_internal(self, node):
        mid = len(node.keys) // 2
        new_internal = BPlusTreeNode(self.order)
        new_internal.keys = node.keys[mid + 1:]
        new_internal.children = node.children[mid + 1:]
        up_key = node.keys[mid]
        node.keys = node.keys[:mid]
        node.children = node.children[:mid + 1]

        if node == self.root:
            new_root = BPlusTreeNode(self.order)
            new_root.keys = [up_key]
            new_root.children = [node, new_internal]
            self.root = new_root
        else:
            self._insert_into_parent(node, up_key, new_internal)

    def _find_parent(self, current, child):
        if current.leaf or current.children[0].leaf:
            return None
        for c in current.children:
            if c == child:
                return current
            res = self._find_parent(c, child)
            if res:
                return res
        return None