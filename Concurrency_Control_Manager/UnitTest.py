import unittest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Concurrency_Control_Manager.classes import ConcurrencyControlManager
from Concurrency_Control_Manager.lib.transaction_model import TransactionStatus
from Storage_Manager.storage_engine import StorageEngine
from Failure_Recovery.failure_recovery_manager import FailureRecoveryManager
from Failure_Recovery.buffer_manager import BufferManager


class TestDeadlockPrevention(unittest.TestCase):

    def setUp(self):
        ConcurrencyControlManager._instance = None

        self.test_dir = tempfile.mkdtemp()
        self.log_dir = os.path.join(self.test_dir, "logs")
        os.makedirs(self.log_dir, exist_ok=True)

        self.buffer_manager = BufferManager()

        def load_table_callback(table_name: str):
            return None

        def save_buffer_callback(data):
            return True

        self.frm = FailureRecoveryManager(
            buffer_manager=self.buffer_manager,
            load_table_callback=load_table_callback,
            save_buffer_callback=save_buffer_callback,
            log_directory=self.log_dir,
            checkpoint_interval=999999,
        )

        self.storage = StorageEngine(
            data_dir=self.test_dir, frm=self.frm, cc_manager=None
        )

        self.ccm = ConcurrencyControlManager(self.frm)
        self.storage.cc_manager = self.ccm

    def tearDown(self):
        ConcurrencyControlManager._instance = None
        if hasattr(self, "frm"):
            self.frm.stop()
        if hasattr(self, "test_dir") and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_wait_die_logic_younger_dies(self):
        print("\n" + "=" * 70)
        print("TEST 1: Wait-Die Logic - Younger Transaction Dies")
        print("=" * 70)

        self.ccm.set_concurrency_mechanism("lock-based")
        self.ccm.strategy.deadlock_prevention_scheme = "wait-die"
        print("Set strategy: Lock-Based with Wait-Die scheme")

        tx1 = self.ccm.begin_transaction()
        print(f"Started T1={tx1} (older)")
        self.ccm.log_object("A", tx1, "read")
        print(f"T1 acquired READ lock on 'A'")

        tx2 = self.ccm.begin_transaction()
        print(f"Started T2={tx2} (younger)")

        print(f"T2 attempting WRITE on 'A' (should die)...")

        with self.assertRaises(Exception) as context:
            self.ccm.log_object("A", tx2, "write")

        print(f"✓ Exception raised: {str(context.exception)}")
        self.assertIn("Wait-Die", str(context.exception))
        self.assertIn("aborted", str(context.exception).lower())

        # Verify T1 is still ACTIVE
        self.assertIn("Wait-Die", str(context.exception))
        self.assertIn("aborted", str(context.exception).lower())

        tx1_status = self.ccm.get_transaction_status(tx1)
        self.assertEqual(tx1_status, TransactionStatus.ACTIVE.value)
        print(f"T1 status: {tx1_status} (still active)")

        self.ccm.commit_transaction(tx1)

        ConcurrencyControlManager._instance = None
        self.ccm = ConcurrencyControlManager(self.frm)
        self.storage.cc_manager = self.ccm

        print("\n✓ TEST 1 PASSED: Younger transaction correctly died in Wait-Die")

    def test_wound_wait_logic_older_wounds_younger(self):
        print("\n" + "=" * 70)
        print("TEST 2: Wound-Wait Logic - Older Wounds Younger")
        print("=" * 70)

        self.ccm.strategy.deadlock_prevention_scheme = "wound-wait"
        print("Set strategy: Wound-Wait scheme")

        tx1 = self.ccm.begin_transaction()
        print(f"Started T1={tx1} (older)")

        tx2 = self.ccm.begin_transaction()
        print(f"Started T2={tx2} (younger)")

        self.ccm.log_object("B", tx2, "read")
        print(f"T2 acquired READ lock on 'B'")

        tx2_status_before = self.ccm.get_transaction_status(tx2)
        self.assertEqual(tx2_status_before, TransactionStatus.ACTIVE.value)
        print(f"T2 status before wound: {tx2_status_before}")

        self.assertLess(tx1, tx2, "T1 should have smaller ID than T2")
        print(f"Verified: T1({tx1}) < T2({tx2})")

        print(f"T1 attempting WRITE on 'B' (should wound T2)...")

        response = self.ccm.validate_object("B", tx1, "write")

        print(f"Validation response for T1: allowed={response.allowed}")

        tx2_status_after = self.ccm.get_transaction_status(tx2)
        print(f"T2 status after wound: {tx2_status_after}")

        self.assertIn(tx2_status_after.lower(), ["aborted", "terminated"])

        self.assertTrue(response.allowed, "T1 should be allowed after wounding T2")
        tx1_status = self.ccm.get_transaction_status(tx1)
        print(f"T1 status: {tx1_status}")
        self.assertEqual(tx1_status, TransactionStatus.ACTIVE.value)

        self.ccm.commit_transaction(tx1)

        print(
            "\n✓ TEST 2 PASSED: Older transaction successfully wounded younger in Wound-Wait"
        )


def run_tests():
    print("\n" + "=" * 70)
    print("DEADLOCK PREVENTION UNIT TESTS")
    print("Testing: Wait-Die and Wound-Wait Schemes")
    print("=" * 70)

    suite = unittest.TestLoader().loadTestsFromTestCase(TestDeadlockPrevention)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 70 + "\n")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)