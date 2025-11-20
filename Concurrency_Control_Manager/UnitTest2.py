import unittest
from datetime import datetime

from lib.transaction_model import TransactionManager, TransactionStatus
from lib.strategy_interface import Response
from lib.lock_based_strategy import LockBasedStrategy
from lib.timestamp_based_strategy import TimestampBasedStrategy
from lib.validation_based_strategy import ValidationBasedStrategy
from lib.multi_version_strategy import MultiVersionStrategy
from lib.end_transaction import EndTransactionManager, EndTransactionResult
from lib.transaction_coordinator import TransactionCoordinator
from classes import ConcurrencyControlManager


class MockObject:
    """Kelas tiruan untuk objek yang diakses transaksi (Row data)."""
    def __init__(self, obj_id):
        self.obj_id = obj_id
    def __str__(self):
        return self.obj_id
    def __repr__(self):
        return f"MockObject({self.obj_id})"


class TestLockBasedConcurrency(unittest.TestCase):
    """Test Lock-Based 2PL Strategy dengan wound-wait deadlock prevention."""
    
    def setUp(self):
        self.ccm = ConcurrencyControlManager()
        self.ccm.set_concurrency_mechanism("lock-based")
        # Disable verbose untuk test yang lebih bersih
        self.ccm.strategy.verbose = False
        self.ccm.coordinator.end_tx_manager.verbose = False
        
    def test_sequential_read_write_commit(self):
        """Test skenario: TX1 READ → COMMIT, TX2 WRITE → COMMIT (seharusnya sukses semua)"""
        
        # TX1: BEGIN → READ → COMMIT
        tx1_id = self.ccm.begin_transaction()
        self.ccm.log_object("A", tx1_id, "read")
        self.ccm.commit_transaction(tx1_id)
        
        tx1 = self.ccm.tx_manager.get_transaction(tx1_id)
        self.assertEqual(tx1.status, TransactionStatus.TERMINATED)
        self.assertIn(tx1_id, self.ccm.tx_manager.committed_transactions)
        
        # TX2: BEGIN → WRITE → COMMIT (lock sudah released oleh TX1)
        tx2_id = self.ccm.begin_transaction()
        self.ccm.log_object("A", tx2_id, "write")
        self.ccm.commit_transaction(tx2_id)
        
        tx2 = self.ccm.tx_manager.get_transaction(tx2_id)
        self.assertEqual(tx2.status, TransactionStatus.TERMINATED)
        self.assertIn(tx2_id, self.ccm.tx_manager.committed_transactions)
        
        print("[PASS] Lock-Based: Sequential Read-Write berhasil tanpa conflict")


class TestTimestampBasedConcurrency(unittest.TestCase):
    """Test Timestamp-Based Strategy."""
    
    def setUp(self):
        self.ccm = ConcurrencyControlManager()
        self.ccm.set_concurrency_mechanism("timestamp-based")
        self.ccm.strategy.verbose = False
        self.ccm.coordinator.end_tx_manager.verbose = False
        
    def test_timestamp_ordering_success(self):
        """Test skenario: TX1(TS=1) WRITE → COMMIT, TX2(TS=2) READ → COMMIT (seharusnya sukses)"""
        
        # TX1 (TS lebih kecil) WRITE first
        tx1_id = self.ccm.begin_transaction()  # TS = 1
        
        # Validate WRITE (TS=1 >= W-TS=0 dan R-TS=0, sukses)
        response = self.ccm.validate_object("X", tx1_id, "write")
        self.assertTrue(response.allowed)
        
        self.ccm.log_object("X", tx1_id, "write")
        self.ccm.commit_transaction(tx1_id)
        
        # TX2 (TS lebih besar) READ
        tx2_id = self.ccm.begin_transaction()  # TS = 2
        
        # Validate READ (TS=2 >= W-TS=1, sukses)
        response = self.ccm.validate_object("X", tx2_id, "read")
        self.assertTrue(response.allowed)
        
        self.ccm.log_object("X", tx2_id, "read")
        self.ccm.commit_transaction(tx2_id)
        
        self.assertEqual(self.ccm.get_transaction_status(tx1_id), "terminated")
        self.assertEqual(self.ccm.get_transaction_status(tx2_id), "terminated")
        
        print("[PASS] Timestamp-Based: Ordering berhasil dengan TS yang benar")


class TestValidationBasedConcurrency(unittest.TestCase):
    """Test Validation-Based (OCC) Strategy."""
    
    def setUp(self):
        self.ccm = ConcurrencyControlManager()
        self.ccm.set_concurrency_mechanism("validation-based")
        self.ccm.strategy.verbose = False
        self.ccm.coordinator.end_tx_manager.verbose = False
        
    def test_occ_no_conflict_commit_success(self):
        """Test skenario: TX1 WRITE A → COMMIT, TX2 WRITE B → COMMIT (no conflict, sukses)"""
        
        # TX1: WRITE A
        tx1_id = self.ccm.begin_transaction()
        
        # OCC: semua operasi diizinkan saat execution phase
        response = self.ccm.validate_object("A", tx1_id, "write")
        self.assertTrue(response.allowed)
        
        self.ccm.log_object("A", tx1_id, "write")
        self.ccm.commit_transaction(tx1_id)
        
        self.assertEqual(self.ccm.get_transaction_status(tx1_id), "terminated")
        self.assertIn(tx1_id, self.ccm.tx_manager.committed_transactions)
        
        # TX2: WRITE B (different object, no conflict)
        tx2_id = self.ccm.begin_transaction()
        
        response = self.ccm.validate_object("B", tx2_id, "write")
        self.assertTrue(response.allowed)
        
        self.ccm.log_object("B", tx2_id, "write")
        self.ccm.commit_transaction(tx2_id)
        
        self.assertEqual(self.ccm.get_transaction_status(tx2_id), "terminated")
        self.assertIn(tx2_id, self.ccm.tx_manager.committed_transactions)
        
        print("[PASS] Validation-Based: No conflict scenario berhasil commit")


class TestMultiVersionConcurrency(unittest.TestCase):
    """Test Multi-Version (MVCC) Strategy."""
    
    def setUp(self):
        self.ccm = ConcurrencyControlManager()
        self.ccm.set_concurrency_mechanism("multi-version")
        self.ccm.strategy.verbose = False
        self.ccm.coordinator.end_tx_manager.verbose = False
        
    def test_mvcc_concurrent_read_write(self):
        """Test skenario: TX1 WRITE → COMMIT, TX2 READ (baca versi lama, sukses)"""
        
        # TX1: WRITE creates new version
        tx1_id = self.ccm.begin_transaction()  # TS = 1
        
        response = self.ccm.validate_object("Y", tx1_id, "write")
        self.assertTrue(response.allowed)
        
        self.ccm.log_object("Y", tx1_id, "write")
        self.ccm.commit_transaction(tx1_id)
        
        self.assertEqual(self.ccm.get_transaction_status(tx1_id), "terminated")
        
        # TX2: READ (will read correct version based on timestamp)
        tx2_id = self.ccm.begin_transaction()  # TS = 2
        
        response = self.ccm.validate_object("Y", tx2_id, "read")
        self.assertTrue(response.allowed)
        
        self.ccm.log_object("Y", tx2_id, "read")
        self.ccm.commit_transaction(tx2_id)
        
        self.assertEqual(self.ccm.get_transaction_status(tx2_id), "terminated")
        
        print("[PASS] Multi-Version: Concurrent read-write berhasil dengan versioning")


class TestTransactionAbort(unittest.TestCase):
    """Test abort functionality across all strategies."""
    
    def setUp(self):
        self.ccm = ConcurrencyControlManager()
        self.ccm.strategy.verbose = False
        self.ccm.coordinator.end_tx_manager.verbose = False
        
    def test_user_initiated_abort(self):
        """Test user-initiated rollback."""
        
        tx_id = self.ccm.begin_transaction()
        self.ccm.log_object("Z", tx_id, "write")
        
        # User decides to abort
        self.ccm.abort_transaction(tx_id, "User rollback")
        
        tx = self.ccm.tx_manager.get_transaction(tx_id)
        self.assertEqual(tx.status, TransactionStatus.TERMINATED)
        self.assertIn(tx_id, self.ccm.tx_manager.aborted_transactions)
        
        print("[PASS] Transaction abort berhasil")


class TestConcurrencyControlManager(unittest.TestCase):
    """Test CCM core functionality."""
    
    def setUp(self):
        self.ccm = ConcurrencyControlManager()
        
    def test_singleton_pattern(self):
        """Test CCM is singleton."""
        ccm2 = ConcurrencyControlManager()
        self.assertIs(self.ccm, ccm2)
        print("[PASS] Singleton pattern works correctly")
        
    def test_strategy_switching(self):
        """Test switching between strategies."""
        
        # Start with lock-based
        self.assertEqual(self.ccm.strategy.__class__.__name__, "LockBasedStrategy")
        
        # Switch to timestamp-based
        self.ccm.set_concurrency_mechanism("timestamp-based")
        self.assertEqual(self.ccm.strategy.__class__.__name__, "TimestampBasedStrategy")
        
        # Switch to validation-based
        self.ccm.set_concurrency_mechanism("validation-based")
        self.assertEqual(self.ccm.strategy.__class__.__name__, "ValidationBasedStrategy")
        
        # Switch to multi-version
        self.ccm.set_concurrency_mechanism("multi-version")
        self.assertEqual(self.ccm.strategy.__class__.__name__, "MultiVersionStrategy")
        
        print("[PASS] Strategy switching works correctly")
        
    def test_transaction_lifecycle(self):
        """Test complete transaction lifecycle."""
        
        # BEGIN
        tx_id = self.ccm.begin_transaction()
        self.assertEqual(self.ccm.get_transaction_status(tx_id), "active")
        
        # OPERATION
        self.ccm.log_object("test_obj", tx_id, "read")
        tx = self.ccm.tx_manager.get_transaction(tx_id)
        self.assertIn("test_obj", tx.read_set)
        
        # COMMIT
        self.ccm.commit_transaction(tx_id)
        self.assertEqual(self.ccm.get_transaction_status(tx_id), "terminated")
        
        print("[PASS] Transaction lifecycle complete")


if __name__ == '__main__':
    print("\n" + "="*70)
    print("CONCURRENCY CONTROL MANAGER - UNIT TESTS")
    print("Testing all 4 concurrency control strategies")
    print("="*70)
    
    print("\n--- Test 1: Lock-Based Strategy (2PL) ---")
    suite_lock = unittest.TestLoader().loadTestsFromTestCase(TestLockBasedConcurrency)
    unittest.TextTestRunner(verbosity=2).run(suite_lock)
    
    print("\n--- Test 2: Timestamp-Based Strategy ---")
    suite_ts = unittest.TestLoader().loadTestsFromTestCase(TestTimestampBasedConcurrency)
    unittest.TextTestRunner(verbosity=2).run(suite_ts)
    
    print("\n--- Test 3: Validation-Based Strategy (OCC) ---")
    suite_occ = unittest.TestLoader().loadTestsFromTestCase(TestValidationBasedConcurrency)
    unittest.TextTestRunner(verbosity=2).run(suite_occ)
    
    print("\n--- Test 4: Multi-Version Strategy (MVCC) ---")
    suite_mvcc = unittest.TestLoader().loadTestsFromTestCase(TestMultiVersionConcurrency)
    unittest.TextTestRunner(verbosity=2).run(suite_mvcc)
    
    print("\n--- Test 5: Transaction Abort ---")
    suite_abort = unittest.TestLoader().loadTestsFromTestCase(TestTransactionAbort)
    unittest.TextTestRunner(verbosity=2).run(suite_abort)
    
    print("\n--- Test 6: CCM Core Functionality ---")
    suite_ccm = unittest.TestLoader().loadTestsFromTestCase(TestConcurrencyControlManager)
    unittest.TextTestRunner(verbosity=2).run(suite_ccm)
    
    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70)
