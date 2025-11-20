from collections import defaultdict
import pickle
import os

class HashIndex:
    def __init__(self):
        self.index = defaultdict(list)

    def insert(self, key: str, value: int):
        self.index[key].append(value)

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