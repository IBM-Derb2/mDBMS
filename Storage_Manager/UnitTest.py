import unittest
from storage_engine import StorageEngine
from Utils import DataRetrieval, DataDeletion, Condition
from serializer import Serializer


class TestStorageEngine(unittest.TestCase):
    def setUp(self):
        self.serializer = Serializer()
        self.storage = StorageEngine(data_dir="data_demo", serializer=self.serializer)

    def test_read_block(self):
        dr = DataRetrieval(
            table="student",
            column=["StudentID", "FullName", "GPA"],
            conditions=[Condition("GPA", ">", 3.5)]
        )
        rows = self.storage.read_block(dr)
        self.assertGreater(rows.rows_count, 0)
        print("Read Block -> OK, hasil:", rows.rows_count)

    def test_get_stats(self):
        stats = self.storage.get_stats("student")
        print(stats)
        self.assertIsNotNone(stats)
        print("Get Stats -> OK")


if __name__ == "__main__":
    unittest.main()
