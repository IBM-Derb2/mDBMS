from typing import Union
import pickle

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
    
    def search(self, key): # returns none or value
        leaf = self._find_leaf(self.root, key)
        for i, k in enumerate(leaf.keys):
            if k == key:
                return leaf.children[i]
        return None

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

    def save(self, filename):
        with open(filename, "wb") as f:
            pickle.dump(self.root, f)

    @staticmethod
    def load(filename):
        with open(filename, "rb") as f:
            tree = BPlusTreeIndex()
            tree.root = pickle.load(f)
            return tree

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