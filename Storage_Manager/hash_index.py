from collections import defaultdict

class HashIndex:
    def __init__(self):
        self.index = defaultdict(list)

    def insert(self, key: str, value: int):
        self.index[key].append(value)

    def search(self, key: str) -> list[int]:
        return self.index.get(key, [])