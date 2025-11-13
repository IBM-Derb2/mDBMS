import unittest
from storage_engine import StorageEngine
from utils import DataRetrieval, Condition
from serializer import Serializer


class TestStorageEngine(unittest.TestCase):
    def setUp(self):
        self.serializer = Serializer()
        self.storage = StorageEngine(data_dir="dummy_data", serializer=self.serializer)

    def test_read_block(self):
        dr = DataRetrieval(
            table="student",
            column=["StudentID", "FullName", "GPA"],
            conditions=[Condition("GPA", ">", 3.5)]
        )
        rows = self.storage.read_block(dr)

        print("\n=== test_read_block Result ===")
        print(f"Rows(")
        print(f"    data=[")
        for i, row in enumerate(rows.data):
            comma = "," if i < len(rows.data) - 1 else ""
            print(f"        {row}{comma}")
        print(f"    ],")
        print(f"    rows_count={rows.rows_count},")
        print(f"    idx={rows.idx}")
        print(f")")

        self.assertGreater(rows.rows_count, 0)

    def test_get_stats(self):
        stats = self.storage.get_stats("student")
        print(stats)
        self.assertIsNotNone(stats)
        print("Get Stats -> OK")


if __name__ == "__main__":
    unittest.main()
