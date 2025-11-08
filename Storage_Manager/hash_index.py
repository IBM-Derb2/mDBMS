from collections import defaultdict

class HashIndex:
    def __init__(self):
        self.index = defaultdict(list)

    def insert(self, key: str, value: int):
        """
        Saves data offsets of key instances in a dictionary
        """
        self.index[key].append(value)

    def search(self, key: str) -> list[int]:
        """
        Retrieve offsets from key
        """
        return self.index.get(key, [])