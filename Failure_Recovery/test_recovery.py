from recovery import RecoveryEngine
from recovery_model import RecoverCriteria
from datetime import datetime

# Pastikan log sudah ditulis dahulu sebelum test. jalankan test_penulisan_log.py terlebih dahulu
print("--- Memulai Simulasi Recovery 1: Criteria Transaction ID ---")
criteria = RecoverCriteria(transaction_id=102)
engine = RecoveryEngine(log_directory="test_logs")
engine.recover(criteria)
print("--- Simulasi Recovery 1 Selesai ---")

print()

print("--- Memulai Simulasi Recovery 2: Timestamp ---")
criteria2 = RecoverCriteria(timestamp=datetime.fromisoformat("2025-11-11T21:28:04.908557")) # harus ada cara untuk memastikan input timestamp berdasarkan iso format
engine.recover(criteria2)
print("--- Simulasi Recovery 2 Selesai ---")