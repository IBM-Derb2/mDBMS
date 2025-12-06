import unittest
import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from Failure_Recovery.buffer_manager import BufferManager
from Failure_Recovery.failure_recovery_manager import FailureRecoveryManager
from Failure_Recovery.frm_types import WalAction
from Storage_Manager.storage_engine import StorageEngine
from Storage_Manager.serializer import Serializer


class TestFailureRecoveryManager(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("\nSetup: Initializing test environment")

        cls.TEST_LOG_DIR = "test_logs"

        if os.path.exists(cls.TEST_LOG_DIR):
            shutil.rmtree(cls.TEST_LOG_DIR)

        os.makedirs(cls.TEST_LOG_DIR, exist_ok=True)

        test_data_dir = "failure_recovery"
        cls.serializer = Serializer()
        cls.storage = StorageEngine(data_dir=test_data_dir, serializer=cls.serializer)

        print("Setup: Complete\n")
    
    def setUp(self):
        self.buffer_manager = BufferManager(capacity=4)

        self.frm = FailureRecoveryManager(
            buffer_manager=self.buffer_manager,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory=self.TEST_LOG_DIR,
            checkpoint_interval=10
        )
    
    def tearDown(self):
        """Cleanup after each test"""

        if self.frm.running:
            self.frm.stop()
    
    def test_01_transaction_start_end(self):
        """Test transaction start and end tracking"""

        self.frm.notify_transaction_start(101)
        self.assertIn(101, self.frm.active_transactions)
        self.assertEqual(len(self.frm.active_transactions), 1)
        
        self.frm.notify_transaction_end(101)
        self.assertNotIn(101, self.frm.active_transactions)
        self.assertEqual(len(self.frm.active_transactions), 0)
    
    def test_02_multiple_active_transactions(self):
        """Test multiple concurrent transactions"""
        
        tx_ids = [201, 202, 203]
        
        # multiple transactions
        for tx_id in tx_ids:
            self.frm.notify_transaction_start(tx_id)
            self.frm.write_log_entry(tx_id, WalAction.START)
        
        self.assertEqual(len(self.frm.active_transactions), 3)
        
        # End one transaction
        self.frm.write_log_entry(201, WalAction.COMMIT)
        self.frm.notify_transaction_end(201)
        
        self.assertEqual(len(self.frm.active_transactions), 2)
        self.assertNotIn(201, self.frm.active_transactions)
        self.assertIn(202, self.frm.active_transactions)
        self.assertIn(203, self.frm.active_transactions)
        
        # End remaining
        for tx_id in [202, 203]:
            self.frm.write_log_entry(tx_id, WalAction.COMMIT)
            self.frm.notify_transaction_end(tx_id)
        
        self.assertEqual(len(self.frm.active_transactions), 0)
    
    
    def test_03_log_insert_operation(self):
        """Test logging INSERT operation"""

        tx_id = 301
        self.frm.notify_transaction_start(tx_id)
        self.frm.write_log_entry(tx_id, WalAction.START)
        
        # log INSERT
        new_data = {"studentid": 99, "fullname": "New_Student", "gpa": 3.8}
        self.frm.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 99},
            old_data=None,
            new_data=new_data
        )
        
        self.frm.write_log_entry(tx_id, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx_id)

        wal_file = os.path.join(self.TEST_LOG_DIR, "wal.log")
        self.assertTrue(os.path.exists(wal_file))
    
    def test_04_log_update_operation(self):
        """Test logging UPDATE operation"""

        tx_id = 401
        self.frm.notify_transaction_start(tx_id)
        self.frm.write_log_entry(tx_id, WalAction.START)
        
        # Log UPDATE
        old_data = {"studentid": 1, "fullname": "Student_1", "gpa": 3.1}
        new_data = {"studentid": 1, "fullname": "Student_1", "gpa": 3.9}
        
        self.frm.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 1},
            old_data=old_data,
            new_data=new_data
        )
        
        self.frm.write_log_entry(tx_id, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx_id)
    
    def test_05_log_delete_operation(self):
        """Test logging DELETE operation"""

        tx_id = 501
        self.frm.notify_transaction_start(tx_id)
        self.frm.write_log_entry(tx_id, WalAction.START)
        
        # Log DELETE
        old_data = {"studentid": 5, "fullname": "Student_5", "gpa": 3.5}
        
        self.frm.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 5},
            old_data=old_data,
            new_data=None
        )
        
        self.frm.write_log_entry(tx_id, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx_id)
    
    def test_06_buffer_integration_read_write(self):
        """Test buffer manager integration with FRM"""

        # read from buffer (cache miss, loads from disk)
        pk_value = {"studentid": 1}
        row = self.buffer_manager.read_block("student", pk_value)
        
        self.assertIsNotNone(row)
        self.assertEqual(row.data["studentid"], 1)
        self.assertFalse(row.is_dirty)
        
        # write to buffer (marks dirty)
        tx_id = 601
        self.frm.notify_transaction_start(tx_id)
        
        new_data = {"studentid": 1, "fullname": "Updated_Student", "gpa": 4.0}
        self.buffer_manager.write_block(tx_id, "student", pk_value, new_data)
        
        # check dirty flag
        buffer_key = self.buffer_manager._get_buffer_key("student", pk_value)
        updated_row = self.buffer_manager.buffer_data[buffer_key]
        self.assertTrue(updated_row.is_dirty)
        
        self.frm.notify_transaction_end(tx_id)
    
    def test_07_buffer_flush_to_disk(self):
        """Test buffer flush to disk"""

        # write to multiple entries
        for i in range(1, 4):
            pk = {"studentid": i}
            new_data = {"studentid": i, "fullname": f"Flushed_{i}", "gpa": 3.5}
            self.buffer_manager.write_block(701 + i, "student", pk, new_data)
        
        # flush
        initial_buffer_size = len(self.buffer_manager.buffer_data)
        self.assertGreater(initial_buffer_size, 0)
        
        # Count dirty blocks before flush
        dirty_count = sum(1 for row in self.buffer_manager.buffer_data.values() if row.is_dirty)
        self.assertEqual(dirty_count, 3)
        
        self.buffer_manager.flush_dirty_blocks()
        
        # After flush: blocks remain cached but no longer dirty
        self.assertEqual(len(self.buffer_manager.buffer_data), 3)
        dirty_after = sum(1 for row in self.buffer_manager.buffer_data.values() if row.is_dirty)
        self.assertEqual(dirty_after, 0)  # All dirty flags should be reset
    
    def test_08_checkpoint_with_active_transactions(self):
        """Test checkpoint with active transactions"""

        # start multiple transactions
        tx_ids = [801, 802, 803]
        for tx_id in tx_ids:
            self.frm.notify_transaction_start(tx_id)
            self.frm.write_log_entry(tx_id, WalAction.START)
            
            # Perform operations
            new_data = {"studentid": tx_id, "fullname": f"TX_{tx_id}", "gpa": 3.5}
            self.frm.log_write(
                tx_id=tx_id,
                table="student",
                pk={"studentid": tx_id},
                old_data=None,
                new_data=new_data
            )
        
        # trigger checkpoint
        ongoing = list(self.frm.active_transactions)
        self.assertEqual(len(ongoing), 3)
        
        self.frm.save_checkpoint(ongoing)

        wal_file = os.path.join(self.TEST_LOG_DIR, "wal.log")
        self.assertTrue(os.path.exists(wal_file))
        
        # end transactions
        for tx_id in tx_ids:
            self.frm.write_log_entry(tx_id, WalAction.COMMIT)
            self.frm.notify_transaction_end(tx_id)
    
    def test_09_checkpoint_commits_after(self):
        """Test transactions committed after checkpoint"""

        # start transaction
        tx_id = 901
        self.frm.notify_transaction_start(tx_id)
        self.frm.write_log_entry(tx_id, WalAction.START)
        
        # operation before checkpoint
        self.frm.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 901},
            old_data=None,
            new_data={"studentid": 901, "fullname": "Before_CP", "gpa": 3.5}
        )
        
        self.frm.save_checkpoint([tx_id])
        
        self.frm.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 901},
            old_data={"studentid": 901, "fullname": "Before_CP", "gpa": 3.5},
            new_data={"studentid": 901, "fullname": "After_CP", "gpa": 3.9}
        )
        
        # commit
        self.frm.write_log_entry(tx_id, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx_id)
    
    
    def test_10_abort_transaction(self):
        """Test transaction abort"""

        tx_id = 1001
        self.frm.notify_transaction_start(tx_id)
        self.frm.write_log_entry(tx_id, WalAction.START)
        
        # perform operations
        self.frm.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 1001},
            old_data=None,
            new_data={"studentid": 1001, "fullname": "Abort_Test", "gpa": 3.5}
        )
        
        # ABORT
        self.frm.abort_transaction(tx_id)
        self.frm.notify_transaction_end(tx_id)
        
        self.assertNotIn(tx_id, self.frm.active_transactions)
    
    def test_11_abort_with_multiple_operations(self):
        """Test abort with multiple operations"""

        tx_id = 1101
        self.frm.notify_transaction_start(tx_id)
        self.frm.write_log_entry(tx_id, WalAction.START)
        
        # INSERT
        self.frm.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 1101},
            old_data=None,
            new_data={"studentid": 1101, "fullname": "Insert_Test", "gpa": 3.5}
        )
        
        # UPDATE
        self.frm.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 1101},
            old_data={"studentid": 1101, "fullname": "Insert_Test", "gpa": 3.5},
            new_data={"studentid": 1101, "fullname": "Update_Test", "gpa": 3.8}
        )
        
        # DELETE another record
        self.frm.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 1},
            old_data={"studentid": 1, "fullname": "Student_1", "gpa": 3.1},
            new_data=None
        )
        
        # ABORT, should undo all operations
        self.frm.abort_transaction(tx_id)
        self.frm.notify_transaction_end(tx_id)
    
    
    def test_12_recovery_committed_transaction(self):
        """Test recovery with committed transaction"""

        if os.path.exists(self.TEST_LOG_DIR):
            shutil.rmtree(self.TEST_LOG_DIR)
        os.makedirs(self.TEST_LOG_DIR, exist_ok=True)

        buffer_manager_test = BufferManager(capacity=4)

        frm_test = FailureRecoveryManager(
            buffer_manager=buffer_manager_test,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory=self.TEST_LOG_DIR,
            checkpoint_interval=10
        )

        tx_id = 1201
        frm_test.notify_transaction_start(tx_id)
        frm_test.write_log_entry(tx_id, WalAction.START)
        
        frm_test.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 1201},
            old_data=None,
            new_data={"studentid": 1201, "fullname": "Committed", "gpa": 3.8}
        )
        
        frm_test.write_log_entry(tx_id, WalAction.COMMIT)
        frm_test.notify_transaction_end(tx_id)
        
        # recovery
        stats = frm_test.recover()
        
        # stats
        self.assertIsNotNone(stats)
        self.assertIn('redo_count', stats)
    
    def test_13_recovery_incomplete_transaction(self):
        """Test recovery with incomplete (crashed) transaction"""

        if os.path.exists(self.TEST_LOG_DIR):
            shutil.rmtree(self.TEST_LOG_DIR)
        os.makedirs(self.TEST_LOG_DIR, exist_ok=True)

        buffer_manager_test = BufferManager(capacity=4)

        frm_test = FailureRecoveryManager(
            buffer_manager=buffer_manager_test,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory=self.TEST_LOG_DIR,
            checkpoint_interval=10
        )

        tx_id = 1301
        frm_test.notify_transaction_start(tx_id)
        frm_test.write_log_entry(tx_id, WalAction.START)
        
        frm_test.log_write(
            tx_id=tx_id,
            table="student",
            pk={"studentid": 1301},
            old_data=None,
            new_data={"studentid": 1301, "fullname": "Incomplete", "gpa": 3.5}
        )
        
        # NO COMMIT, simulate crash
        
        stats = frm_test.recover()
        
        # should have undo operations for incomplete transaction
        self.assertIn('undo_count', stats)
    
    def test_14_recovery_with_checkpoint(self):
        """Test recovery with checkpoint"""

        if os.path.exists(self.TEST_LOG_DIR):
            shutil.rmtree(self.TEST_LOG_DIR)
        os.makedirs(self.TEST_LOG_DIR, exist_ok=True)

        buffer_manager_test = BufferManager(capacity=4)

        frm_test = FailureRecoveryManager(
            buffer_manager=buffer_manager_test,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory=self.TEST_LOG_DIR,
            checkpoint_interval=10
        )

        tx1 = 1401
        frm_test.notify_transaction_start(tx1)
        frm_test.write_log_entry(tx1, WalAction.START)
        frm_test.log_write(tx1, "student", {"studentid": 1401}, None,
                          {"studentid": 1401, "fullname": "Before_CP", "gpa": 3.5})
        frm_test.write_log_entry(tx1, WalAction.COMMIT)
        frm_test.notify_transaction_end(tx1)
        
        # TX 2: Start before checkpoint
        tx2 = 1402
        frm_test.notify_transaction_start(tx2)
        frm_test.write_log_entry(tx2, WalAction.START)
        frm_test.log_write(tx2, "student", {"studentid": 1402}, None,
                          {"studentid": 1402, "fullname": "Ongoing", "gpa": 3.5})
        
        # CHECKPOINT
        frm_test.save_checkpoint([tx2])
        
        # TX 2: Continue after checkpoint and commit
        frm_test.log_write(tx2, "student", {"studentid": 1402},
                          {"studentid": 1402, "fullname": "Ongoing", "gpa": 3.5},
                          {"studentid": 1402, "fullname": "After_CP", "gpa": 3.9})
        frm_test.write_log_entry(tx2, WalAction.COMMIT)
        frm_test.notify_transaction_end(tx2)
        
        # TX 3: After checkpoint, no commit (crash)
        tx3 = 1403
        frm_test.notify_transaction_start(tx3)
        frm_test.write_log_entry(tx3, WalAction.START)
        frm_test.log_write(tx3, "student", {"studentid": 1403}, None,
                          {"studentid": 1403, "fullname": "Crash", "gpa": 3.5})
        
        # Simulate crash, no commit for tx3
        
        # Recovery
        stats = frm_test.recover()
        
        self.assertTrue(stats['checkpoint_found'])
        self.assertIn('redo_count', stats)
        self.assertIn('undo_count', stats)
    
    
    def test_15_full_workflow_insert_update_delete(self):
        """Test full workflow: INSERT, UPDATE, DELETE with FRM"""

        # Transaction 1: INSERT
        tx1 = 1501
        self.frm.notify_transaction_start(tx1)
        self.frm.write_log_entry(tx1, WalAction.START)
        
        self.frm.log_write(
            tx_id=tx1,
            table="student",
            pk={"studentid": 1501},
            old_data=None,
            new_data={"studentid": 1501, "fullname": "Workflow_Test", "gpa": 3.5}
        )
        
        self.frm.write_log_entry(tx1, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx1)
        
        # Transaction 2: UPDATE
        tx2 = 1502
        self.frm.notify_transaction_start(tx2)
        self.frm.write_log_entry(tx2, WalAction.START)
        
        self.frm.log_write(
            tx_id=tx2,
            table="student",
            pk={"studentid": 1501},
            old_data={"studentid": 1501, "fullname": "Workflow_Test", "gpa": 3.5},
            new_data={"studentid": 1501, "fullname": "Updated_Workflow", "gpa": 3.9}
        )
        
        self.frm.write_log_entry(tx2, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx2)
        
        # Transaction 3: DELETE
        tx3 = 1503
        self.frm.notify_transaction_start(tx3)
        self.frm.write_log_entry(tx3, WalAction.START)
        
        self.frm.log_write(
            tx_id=tx3,
            table="student",
            pk={"studentid": 1501},
            old_data={"studentid": 1501, "fullname": "Updated_Workflow", "gpa": 3.9},
            new_data=None
        )
        
        self.frm.write_log_entry(tx3, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx3)
    
    def test_16_concurrent_transactions_mixed_outcomes(self):
        """Test concurrent transactions with mixed outcomes (commit/abort/crash)"""

        # TX 1: Will commit
        tx1 = 1601
        self.frm.notify_transaction_start(tx1)
        self.frm.write_log_entry(tx1, WalAction.START)
        self.frm.log_write(tx1, "student", {"studentid": 1601}, None,
                          {"studentid": 1601, "fullname": "TX1_Commit", "gpa": 3.5})
        
        # TX 2: Will abort
        tx2 = 1602
        self.frm.notify_transaction_start(tx2)
        self.frm.write_log_entry(tx2, WalAction.START)
        self.frm.log_write(tx2, "student", {"studentid": 1602}, None,
                          {"studentid": 1602, "fullname": "TX2_Abort", "gpa": 3.5})
        
        # TX 3: Will crash (no commit/abort)
        tx3 = 1603
        self.frm.notify_transaction_start(tx3)
        self.frm.write_log_entry(tx3, WalAction.START)
        self.frm.log_write(tx3, "student", {"studentid": 1603}, None,
                          {"studentid": 1603, "fullname": "TX3_Crash", "gpa": 3.5})
        
        # Commit TX1
        self.frm.write_log_entry(tx1, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx1)
        
        # Abort TX2
        self.frm.abort_transaction(tx2)
        self.frm.notify_transaction_end(tx2)
        
        # TX3 crashes (no commit/abort)
        
        # Verify states
        self.assertNotIn(tx1, self.frm.active_transactions)
        self.assertNotIn(tx2, self.frm.active_transactions)
        self.assertIn(tx3, self.frm.active_transactions)  # Still active (crashed)
    
    @classmethod
    def tearDownClass(cls):
        print("\nCleanup: Removing test directories")

        if os.path.exists(cls.TEST_LOG_DIR):
            shutil.rmtree(cls.TEST_LOG_DIR)

        print("Cleanup: Complete")


if __name__ == "__main__":
    # Run with verbosity
    verbosity = 2
    
    if len(sys.argv) > 1:
        try:
            v = int(sys.argv[1])
            if v in (0, 1, 2):
                verbosity = v
        except ValueError:
            pass
        sys.argv = sys.argv[:1]
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFailureRecoveryManager)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    if not result.wasSuccessful():
        sys.exit(1)
