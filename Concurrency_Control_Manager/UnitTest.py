import unittest
from datetime import datetime

from lib.transaction_model import TransactionManager, TransactionStatus
from lib.strategy_interface import Response
from lib.lock_based_strategy import LockBasedStrategy, LockEntry
from lib.validation_based_strategy import ValidationBasedStrategy
from lib.end_transaction import EndTransactionManager, EndTransactionReport


class MockObject:
    """Kelas tiruan untuk objek yang diakses transaksi (Row data)."""

    def __init__(self, obj_id):
        self.obj_id = obj_id

    def __str__(self):
        return self.obj_id

    def __repr__(self):
        return f"MockObject({self.obj_id})"


class TestTransactionManager(unittest.TestCase):
    """uji fungsi dasar TransactionManager."""

    def setUp(self):
        self.manager = TransactionManager()

    def test_create_and_get_transaction(self):
        tx1 = self.manager.create_transaction(1)
        self.assertIsNotNone(tx1)
        self.assertEqual(tx1.transaction_id, 1)
        self.assertEqual(tx1.status, TransactionStatus.ACTIVE)
        self.assertIn(1, self.manager.active_transactions)

    def test_commit_and_abort(self):
        # Commit flow (TX 2)
        tx2 = self.manager.create_transaction(2)
        # commit_transaction akan memanggil mark_partially_committed
        self.manager.commit_transaction(2)
        self.assertEqual(tx2.status, TransactionStatus.COMMITTED)
        self.assertIn(2, self.manager.committed_transactions)

        # Abort flow (TX 3)
        tx3 = self.manager.create_transaction(3)
        self.manager.abort_transaction(3)
        self.assertEqual(tx3.status, TransactionStatus.ABORTED)
        self.assertIn(3, self.manager.aborted_transactions)

    def test_add_operation(self):
        tx4 = self.manager.create_transaction(4)
        tx4.add_operation("read", "A")
        tx4.add_operation("write", "B")
        self.assertIn("A", tx4.read_set)
        self.assertIn("B", tx4.write_set)
        self.assertEqual(len(tx4.operations), 2)

    def test_terminate_transaction(self):
        tx5 = self.manager.create_transaction(5)
        self.manager.commit_transaction(5)
        self.manager.terminate_transaction(5)
        self.assertEqual(
            self.manager.get_transaction(5).status, TransactionStatus.TERMINATED
        )


class TestLockBasedStrategy(unittest.TestCase):
    """uji logika dasar Lock Based Strategy."""

    def setUp(self):
        self.strategy = LockBasedStrategy()
        self.obj_x = MockObject("X")
        self.strategy.verbose = False

    def test_read_lock_acquisition_and_share(self):
        # TX 1 ambil READ lock
        self.strategy.log_object(self.obj_x, 1, "READ")
        self.assertEqual(self.strategy.lock_table["X"].lock_type, "read")

        # TX 2 ambil READ lock (shared)
        self.strategy.log_object(self.obj_x, 2, "read")
        self.assertIn(2, self.strategy.lock_table["X"].holders)
        self.assertEqual(len(self.strategy.lock_table["X"].holders), 2)

    def test_write_lock_conflict_and_validation(self):
        # TX 1 WRITE lock X
        self.strategy.log_object(self.obj_x, 1, "WRITE")

        # TX 2 mencoba READ X (Validasi harus DITOLAK)
        response_read = self.strategy.validate_object(self.obj_x, 2, "READ")
        self.assertFalse(response_read.allowed)

        # TX 2 mencoba WRITE X (Validasi harus DITOLAK)
        response_write = self.strategy.validate_object(self.obj_x, 2, "WRITE")
        self.assertFalse(response_write.allowed)

    def test_lock_release(self):
        # TX 1 WRITE lock X
        self.strategy.log_object(self.obj_x, 1, "WRITE")

        # TX 1 selesai
        self.strategy.end_transaction(1)
        self.assertNotIn("X", self.strategy.lock_table)  # Lock harusnya hilang


class TestEndTransactionManager(unittest.TestCase):
    """
    uji alur end_transaction dan logika validasi final
    yang ada di dalamnya.
    """

    def setUp(self):
        self.tx_manager = TransactionManager()
        self.strategy = ValidationBasedStrategy()
        self.manager = EndTransactionManager(self.tx_manager, self.strategy)
        self.manager.verbose = False

        # Setup 2 TX Committed untuk skenario konflik OCC
        self.tx_manager.create_transaction(10)
        self.tx_manager.transactions[10].read_set = {"A"}
        self.tx_manager.transactions[10].write_set = {"Z"}
        self.tx_manager.commit_transaction(10)  # Status: COMMITTED

        self.tx_manager.create_transaction(11)
        self.tx_manager.transactions[11].read_set = {"B"}
        self.tx_manager.transactions[11].write_set = {"Y"}
        self.tx_manager.commit_transaction(11)  # Status: COMMITTED

        self.tx_manager.committed_transactions = {10, 11}

    # def test_commit_failure_due_to_ww_conflict(self):
    #     tx_id = 1
    #     tx1 = self.tx_manager.create_transaction(tx_id)

    #     # TX 1 menulis objek 'Y' (konflik W-W dengan TX 11 yang sudah COMMIT)
    #     tx1.add_operation("write", "Y")

    #     # Commit harusnya gagal
    #     report = self.manager.end_transaction(tx_id, is_commit=True)

    #     # Commit GAGAL karena validasi, status harus ABORTED
    #     self.assertEqual(report.result, EndTransactionResult.VALIDATION_FAILED)
    #     final_tx_status = self.tx_manager.get_transaction(tx_id).status
    #     self.assertEqual(final_tx_status, TransactionStatus.TERMINATED)
    #     self.assertIn("Write-Write conflict dengan TX 11 pada objek: {'Y'}", report.validation_errors)

    def test_commit_success(self):
        tx_id = 2
        tx2 = self.tx_manager.create_transaction(tx_id)

        # TX 2 menulis objek 'P' (tidak ada konflik)
        tx2.add_operation("write", "P")

        # Commit seharusnya berhasil
        report = self.manager.end_transaction(tx_id, is_commit=True)

        self.assertTrue(report.success)
        self.assertEqual(
            self.tx_manager.get_transaction(tx_id).status, TransactionStatus.TERMINATED
        )
        self.assertIn(tx_id, self.tx_manager.committed_transactions)

    def test_successful_abort_flow(self):
        tx_id = 3
        self.tx_manager.create_transaction(tx_id)

        # Log beberapa operasi (untuk memastikan strategy cleanup)
        self.strategy.log_object("A", tx_id, "read")

        # Lakukan Abort
        report = self.manager.end_transaction(tx_id, is_commit=False)

        # Abort harusnya SUCCESS (melakukan cleanup)
        self.assertTrue(report.success)
        # Status harus ABORTED lalu TERMINATED
        self.assertEqual(
            self.tx_manager.get_transaction(tx_id).status, TransactionStatus.TERMINATED
        )
        # Pastikan cleanup strategy dilakukan
        self.assertNotIn(tx_id, self.strategy.transaction_sets)


if __name__ == "__main__":

    print("\n" + "=" * 50)
    print("Mulai Pengujian Komponen mDBMS (Milestone 1 Stub)")
    print("=" * 50)

    print("\n--- TestTransactionManager ---")
    suite_tx = unittest.TestLoader().loadTestsFromTestCase(TestTransactionManager)
    unittest.TextTestRunner(verbosity=2).run(suite_tx)

    print("\n--- TestLockBasedStrategy (Stub) ---")
    suite_lock = unittest.TestLoader().loadTestsFromTestCase(TestLockBasedStrategy)
    unittest.TextTestRunner(verbosity=2).run(suite_lock)

    print("\n--- TestEndTransactionManager (Alur Commit/Abort & Validasi OCC) ---")
    suite_end = unittest.TestLoader().loadTestsFromTestCase(TestEndTransactionManager)
    unittest.TextTestRunner(verbosity=2).run(suite_end)

    print("\n" + "=" * 50)
    print("Pengujian Selesai")
    print("=" * 50)
