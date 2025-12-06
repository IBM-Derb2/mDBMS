import unittest
import os
import sys
import shutil
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from Failure_Recovery.buffer_manager import BufferManager
from Failure_Recovery.failure_recovery_manager import FailureRecoveryManager
from Failure_Recovery.frm_types import WalAction
from Storage_Manager.storage_engine import StorageEngine
from Storage_Manager.serializer import Serializer


class TestFailureRecoveryIntegration(unittest.TestCase):
    """
    Integration tests for Failure Recovery system.
    Tests interaction between: Buffer Manager, FRM, Recovery Engine, WAL, and Storage.
    """

    @classmethod
    def setUpClass(cls):
        print("\n" + "="*70)
        print("FAILURE RECOVERY INTEGRATION TESTS")
        print("="*70)

        cls.TEST_LOG_DIR = "integration_test_logs"
        cls.TEST_DATA_DIR = "integration_test_data"

        if os.path.exists(cls.TEST_LOG_DIR):
            shutil.rmtree(cls.TEST_LOG_DIR)
        if os.path.exists(cls.TEST_DATA_DIR):
            shutil.rmtree(cls.TEST_DATA_DIR)

        os.makedirs(cls.TEST_LOG_DIR, exist_ok=True)
        os.makedirs(cls.TEST_DATA_DIR, exist_ok=True)

        cls.serializer = Serializer()
        cls.storage = StorageEngine(serializer=cls.serializer, data_dir=cls.TEST_DATA_DIR)

        # Create test table
        schema = {
            "table_name": "test_table",
            "columns": [
                {"name": "id", "type": "int", "primary_key": True},
                {"name": "name", "type": "varchar", "length": 50},
                {"name": "value", "type": "int"}
            ]
        }
        cls.storage.write_table("test_table", schema)

        print("Setup complete: Test environment initialized\n")

    def setUp(self):
        """Setup fresh FRM and buffer for each test"""
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
        
        # Clear logs between tests
        if os.path.exists(self.TEST_LOG_DIR):
            shutil.rmtree(self.TEST_LOG_DIR)
        os.makedirs(self.TEST_LOG_DIR, exist_ok=True)

    # ========== INTEGRATION TEST 1: Full Transaction Lifecycle ==========
    
    def test_01_full_transaction_lifecycle(self):
        """
        Integration: Complete transaction lifecycle from start to commit
        Tests: Buffer write → WAL logging → Flush to disk
        """
        print("\n[Test 01] Full Transaction Lifecycle")

        tx_id = 101
        
        # Start transaction
        self.frm.notify_transaction_start(tx_id)
        self.frm.write_log_entry(tx_id, WalAction.START)
        
        # Write to buffer AND log to WAL
        new_data = {"id": 1, "name": "Test", "value": 100}
        self.buffer_manager.write_block(
            transaction_id=tx_id,
            table_name="test_table",
            pk_value={"id": 1},
            new_data=new_data
        )
        
        # Verify buffer has data
        buffered_row = self.frm.get_buffered_row("test_table", {"id": 1})
        self.assertIsNotNone(buffered_row)
        self.assertEqual(buffered_row["name"], "Test")
        
        # Commit
        self.frm.write_log_entry(tx_id, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx_id)
        
        # Flush to disk
        self.buffer_manager.flush_dirty_blocks()
        
        # Verify data persisted
        self.assertNotIn(tx_id, self.frm.active_transactions)
        
        print("[Test 01] ✓ Transaction lifecycle completed")

    # ========== INTEGRATION TEST 2: Crash Recovery (REDO) ==========
    
    def test_02_crash_recovery_redo_committed(self):
        """
        Integration: Crash after commit but before flush
        Tests: Recovery REDO phase restores committed data
        """
        print("\n[Test 02] Crash Recovery - REDO committed transaction")

        # Transaction 1: Commit
        tx1 = 201
        self.frm.notify_transaction_start(tx1)
        self.frm.write_log_entry(tx1, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx1,
            table_name="test_table",
            pk_value={"id": 2},
            new_data={"id": 2, "name": "Committed", "value": 200}
        )
        
        self.frm.write_log_entry(tx1, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx1)
        
        # SIMULATE CRASH: Don't flush buffer
        
        # Create new FRM (simulates restart)
        new_buffer = BufferManager(capacity=4)
        new_frm = FailureRecoveryManager(
            buffer_manager=new_buffer,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory=self.TEST_LOG_DIR,
            checkpoint_interval=10
        )
        
        # Recovery
        stats = new_frm.recover()
        
        # Verify
        self.assertTrue(stats['recovered'])
        self.assertGreater(stats['redo_count'], 0)
        self.assertEqual(stats['undo_count'], 0)
        
        # Verify data recovered
        recovered_data = new_frm.get_buffered_row("test_table", {"id": 2})
        self.assertIsNotNone(recovered_data)
        self.assertEqual(recovered_data["name"], "Committed")
        
        print("[Test 02] ✓ REDO recovery successful")

    # ========== INTEGRATION TEST 3: Crash Recovery (UNDO) ==========
    
    def test_03_crash_recovery_undo_uncommitted(self):
        """
        Integration: Crash before commit
        Tests: Recovery UNDO phase rolls back uncommitted data
        """
        print("\n[Test 03] Crash Recovery - UNDO uncommitted transaction")

        # Transaction: No commit (crash)
        tx1 = 301
        self.frm.notify_transaction_start(tx1)
        self.frm.write_log_entry(tx1, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx1,
            table_name="test_table",
            pk_value={"id": 3},
            new_data={"id": 3, "name": "Uncommitted", "value": 300}
        )
        
        # SIMULATE CRASH: No commit
        
        # Recovery
        new_buffer = BufferManager(capacity=4)
        new_frm = FailureRecoveryManager(
            buffer_manager=new_buffer,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory=self.TEST_LOG_DIR,
            checkpoint_interval=10
        )
        
        stats = new_frm.recover()
        
        # Verify
        self.assertTrue(stats['recovered'])
        self.assertGreater(stats['undo_count'], 0)
        
        # Verify data NOT in buffer (undone)
        recovered_data = new_frm.get_buffered_row("test_table", {"id": 3})
        self.assertIsNone(recovered_data)
        
        print("[Test 03] ✓ UNDO recovery successful")

    # ========== INTEGRATION TEST 4: Checkpoint Integration ==========
    
    def test_04_checkpoint_integration(self):
        """
        Integration: Checkpoint during active transactions
        Tests: Buffer flush → WAL checkpoint → WAL cleanup
        """
        print("\n[Test 04] Checkpoint Integration")

        # Transaction 1: Commit before checkpoint
        tx1 = 401
        self.frm.notify_transaction_start(tx1)
        self.frm.write_log_entry(tx1, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx1,
            table_name="test_table",
            pk_value={"id": 4},
            new_data={"id": 4, "name": "Before_CP", "value": 400}
        )
        
        self.frm.write_log_entry(tx1, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx1)
        
        # Transaction 2: Active during checkpoint
        tx2 = 402
        self.frm.notify_transaction_start(tx2)
        self.frm.write_log_entry(tx2, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx2,
            table_name="test_table",
            pk_value={"id": 5},
            new_data={"id": 5, "name": "During_CP", "value": 500}
        )
        
        # Trigger checkpoint
        self.frm.save_checkpoint([tx2])
        
        # Verify checkpoint created
        wal_file = os.path.join(self.TEST_LOG_DIR, "wal.log")
        self.assertTrue(os.path.exists(wal_file))
        
        # Transaction 2: Continue after checkpoint - UPDATE
        self.buffer_manager.write_block(
            transaction_id=tx2,
            table_name="test_table",
            pk_value={"id": 5},
            new_data={"id": 5, "name": "After_CP", "value": 550}
        )
        
        self.frm.write_log_entry(tx2, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx2)
        
        print("[Test 04] ✓ Checkpoint integration successful")

    # ========== INTEGRATION TEST 5: Recovery After Checkpoint ==========
    
    def test_05_recovery_from_checkpoint(self):
        """
        Integration: Recovery starts from checkpoint
        Tests: Find checkpoint → REDO after checkpoint → UNDO incomplete
        """
        print("\n[Test 05] Recovery From Checkpoint")

        # TX1: Commit before checkpoint
        tx1 = 501
        self.frm.notify_transaction_start(tx1)
        self.frm.write_log_entry(tx1, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx1,
            table_name="test_table",
            pk_value={"id": 6},
            new_data={"id": 6, "name": "Before_CP", "value": 600}
        )
        
        self.frm.write_log_entry(tx1, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx1)
        
        # TX2: Active during checkpoint
        tx2 = 502
        self.frm.notify_transaction_start(tx2)
        self.frm.write_log_entry(tx2, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx2,
            table_name="test_table",
            pk_value={"id": 7},
            new_data={"id": 7, "name": "During_CP", "value": 700}
        )
        
        # Checkpoint
        self.frm.save_checkpoint([tx2])
        
        # TX2: Commit after checkpoint
        self.frm.write_log_entry(tx2, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx2)
        
        # TX3: Start and crash after checkpoint
        tx3 = 503
        self.frm.notify_transaction_start(tx3)
        self.frm.write_log_entry(tx3, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx3,
            table_name="test_table",
            pk_value={"id": 8},
            new_data={"id": 8, "name": "Crash_After_CP", "value": 800}
        )
        # No commit - crash
        
        # Recovery
        new_buffer = BufferManager(capacity=4)
        new_frm = FailureRecoveryManager(
            buffer_manager=new_buffer,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory=self.TEST_LOG_DIR,
            checkpoint_interval=10
        )
        
        stats = new_frm.recover()
        
        # Verify
        self.assertTrue(stats['checkpoint_found'])
        self.assertIn(tx2, stats['checkpoint_transactions'])
        self.assertGreater(stats['redo_count'], 0)
        self.assertGreater(stats['undo_count'], 0)
        
        print("[Test 05] ✓ Checkpoint recovery successful")

    # ========== INTEGRATION TEST 6: Transaction Abort & Rollback ==========
    
    def test_06_transaction_abort_rollback(self):
        """
        Integration: Abort transaction with rollback
        Tests: Write operations → Abort → UNDO → Flush
        """
        print("\n[Test 06] Transaction Abort & Rollback")

        tx_id = 601
        self.frm.notify_transaction_start(tx_id)
        self.frm.write_log_entry(tx_id, WalAction.START)
        
        # INSERT
        self.buffer_manager.write_block(
            transaction_id=tx_id,
            table_name="test_table",
            pk_value={"id": 9},
            new_data={"id": 9, "name": "Insert", "value": 900}
        )
        
        # UPDATE
        self.buffer_manager.write_block(
            transaction_id=tx_id,
            table_name="test_table",
            pk_value={"id": 9},
            new_data={"id": 9, "name": "Update", "value": 950}
        )
        
        # Verify data in buffer
        buffered = self.frm.get_buffered_row("test_table", {"id": 9})
        self.assertIsNotNone(buffered)
        
        # Abort
        self.frm.abort_transaction(tx_id)
        self.frm.notify_transaction_end(tx_id)
        
        # Verify data removed from buffer
        buffered_after = self.frm.get_buffered_row("test_table", {"id": 9})
        self.assertIsNone(buffered_after)
        
        print("[Test 06] ✓ Abort & rollback successful")

    # ========== INTEGRATION TEST 7: Multiple Concurrent Transactions ==========
    
    def test_07_concurrent_transactions_mixed_outcomes(self):
        """
        Integration: Multiple transactions with different outcomes
        Tests: TX1 commit, TX2 abort, TX3 crash → Recovery
        """
        print("\n[Test 07] Concurrent Transactions - Mixed Outcomes")

        # TX1: Will commit
        tx1 = 701
        self.frm.notify_transaction_start(tx1)
        self.frm.write_log_entry(tx1, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx1,
            table_name="test_table",
            pk_value={"id": 10},
            new_data={"id": 10, "name": "TX1_Commit", "value": 1000}
        )
        
        self.frm.write_log_entry(tx1, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx1)
        
        # TX2: Will abort
        tx2 = 702
        self.frm.notify_transaction_start(tx2)
        self.frm.write_log_entry(tx2, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx2,
            table_name="test_table",
            pk_value={"id": 11},
            new_data={"id": 11, "name": "TX2_Abort", "value": 1100}
        )
        
        self.frm.abort_transaction(tx2)
        self.frm.notify_transaction_end(tx2)
        
        # TX3: Will crash
        tx3 = 703
        self.frm.notify_transaction_start(tx3)
        self.frm.write_log_entry(tx3, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx3,
            table_name="test_table",
            pk_value={"id": 12},
            new_data={"id": 12, "name": "TX3_Crash", "value": 1200}
        )
        # No commit - crash
        
        # Recovery
        new_buffer = BufferManager(capacity=4)
        new_frm = FailureRecoveryManager(
            buffer_manager=new_buffer,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory=self.TEST_LOG_DIR,
            checkpoint_interval=10
        )
        
        stats = new_frm.recover()
        
        # Verify outcomes
        self.assertTrue(stats['recovered'])
        
        # TX1 should be recovered
        tx1_data = new_frm.get_buffered_row("test_table", {"id": 10})
        self.assertIsNotNone(tx1_data)
        
        # TX2 should not exist (aborted) - sudah di-rollback sebelum crash
        # Jadi setelah recovery juga tidak ada
        tx2_data = new_frm.get_buffered_row("test_table", {"id": 11})
        self.assertIsNone(tx2_data)
        
        # TX3 should be undone
        tx3_data = new_frm.get_buffered_row("test_table", {"id": 12})
        self.assertIsNone(tx3_data)
        
        print("[Test 07] ✓ Concurrent transactions handled correctly")

    # ========== INTEGRATION TEST 8: Buffer Overflow & Auto Checkpoint ==========
    
    def test_08_buffer_overflow_auto_checkpoint(self):
        """
        Integration: Fill buffer to trigger automatic checkpoint
        Tests: Buffer full → Auto checkpoint → Flush → Continue
        """
        print("\n[Test 08] Buffer Overflow & Auto Checkpoint")

        # Start checkpoint routine
        self.frm.start()
        
        # Fill buffer beyond capacity
        for i in range(10):
            tx_id = 800 + i
            self.frm.notify_transaction_start(tx_id)
            self.frm.write_log_entry(tx_id, WalAction.START)
            
            self.buffer_manager.write_block(
                transaction_id=tx_id,
                table_name="test_table",
                pk_value={"id": 20 + i},
                new_data={"id": 20 + i, "name": f"Overflow_{i}", "value": 2000 + i}
            )
            
            self.frm.write_log_entry(tx_id, WalAction.COMMIT)
            self.frm.notify_transaction_end(tx_id)
        
        # Wait for checkpoint to trigger
        time.sleep(0.5)
        
        # Verify buffer handled overflow
        self.assertLessEqual(len(self.buffer_manager.buffer_data), self.buffer_manager.capacity)
        
        self.frm.stop()
        
        print("[Test 08] ✓ Buffer overflow handled with checkpoint")

    # ========== INTEGRATION TEST 9: UPDATE Operations Chain ==========
    
    def test_09_update_operations_chain(self):
        """
        Integration: Multiple updates on same record
        Tests: INSERT → UPDATE → UPDATE → Commit → Flush → Recovery
        """
        print("\n[Test 09] UPDATE Operations Chain")

        tx_id = 901
        self.frm.notify_transaction_start(tx_id)
        self.frm.write_log_entry(tx_id, WalAction.START)
        
        # INSERT
        self.buffer_manager.write_block(
            transaction_id=tx_id,
            table_name="test_table",
            pk_value={"id": 30},
            new_data={"id": 30, "name": "Initial", "value": 3000}
        )
        
        # UPDATE 1
        self.buffer_manager.write_block(
            transaction_id=tx_id,
            table_name="test_table",
            pk_value={"id": 30},
            new_data={"id": 30, "name": "Updated1", "value": 3100}
        )
        
        # UPDATE 2
        self.buffer_manager.write_block(
            transaction_id=tx_id,
            table_name="test_table",
            pk_value={"id": 30},
            new_data={"id": 30, "name": "Updated2", "value": 3200}
        )
        
        # Commit
        self.frm.write_log_entry(tx_id, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx_id)
        
        # Flush to disk BEFORE checkpoint
        self.buffer_manager.flush_dirty_blocks()
        
        # Checkpoint AFTER flush
        self.frm.save_checkpoint([])
        
        # Recovery
        new_buffer = BufferManager(capacity=4)
        new_frm = FailureRecoveryManager(
            buffer_manager=new_buffer,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory=self.TEST_LOG_DIR,
            checkpoint_interval=10
        )
        
        stats = new_frm.recover()
        
        # After checkpoint with no ongoing transactions, WAL is cleared
        # Recovery should find checkpoint but no operations to redo
        # So we need to read from disk instead
        self.assertTrue(stats['checkpoint_found'])
        
        # Data should be on disk, load it
        from Storage_Manager.utils import DataRetrieval
        result = self.storage.read_block(DataRetrieval(
            table="test_table",
            column=["*"],
            conditions=[]
        ))
        
        # Find our record
        final_data = None
        for row in result.data:
            if row.get('id') == 30:
                final_data = row
                break
        
        self.assertIsNotNone(final_data)
        self.assertEqual(final_data["name"], "Updated2")
        self.assertEqual(final_data["value"], 3200)
        
        print("[Test 09] ✓ UPDATE chain handled correctly")

    # ========== INTEGRATION TEST 10: DELETE Operations ==========
    
    def test_10_delete_operations_integration(self):
        """
        Integration: INSERT → DELETE workflow
        Tests: Buffer tombstone → Flush → Recovery
        """
        print("\n[Test 10] DELETE Operations Integration")

        # First, insert data
        tx1 = 1001
        self.frm.notify_transaction_start(tx1)
        self.frm.write_log_entry(tx1, WalAction.START)
        
        self.buffer_manager.write_block(
            transaction_id=tx1,
            table_name="test_table",
            pk_value={"id": 40},
            new_data={"id": 40, "name": "ToDelete", "value": 4000}
        )
        
        self.frm.write_log_entry(tx1, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx1)
        self.buffer_manager.flush_dirty_blocks()
        
        # Then delete
        tx2 = 1002
        self.frm.notify_transaction_start(tx2)
        self.frm.write_log_entry(tx2, WalAction.START)
        
        self.buffer_manager.delete_block(
            transaction_id=tx2,
            table_name="test_table",
            pk_value={"id": 40},
            old_data={"id": 40, "name": "ToDelete", "value": 4000}
        )
        
        self.frm.write_log_entry(tx2, WalAction.COMMIT)
        self.frm.notify_transaction_end(tx2)
        
        # Recovery
        new_buffer = BufferManager(capacity=4)
        new_frm = FailureRecoveryManager(
            buffer_manager=new_buffer,
            load_table_callback=self.storage.read_disk_to_buffer,
            save_buffer_callback=self.storage.save_buffer_to_disk,
            log_directory=self.TEST_LOG_DIR,
            checkpoint_interval=10
        )
        
        stats = new_frm.recover()
        
        # Verify data deleted
        deleted_data = new_frm.get_buffered_row("test_table", {"id": 40})
        self.assertIsNone(deleted_data)
        
        print("[Test 10] ✓ DELETE operations handled correctly")

    @classmethod
    def tearDownClass(cls):
        print("\n" + "="*70)
        print("Cleanup: Removing test directories")
        
        if os.path.exists(cls.TEST_LOG_DIR):
            shutil.rmtree(cls.TEST_LOG_DIR)
        if os.path.exists(cls.TEST_DATA_DIR):
            shutil.rmtree(cls.TEST_DATA_DIR)
        
        print("Cleanup complete")
        print("="*70)


if __name__ == "__main__":
    # Run with high verbosity
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFailureRecoveryIntegration)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "="*70)
    print("INTEGRATION TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)
    
    if not result.wasSuccessful():
        sys.exit(1)