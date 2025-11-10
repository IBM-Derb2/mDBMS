
from log_config import ActionType, MockChangeReport
from log_writer import LogWriter

log_writer = LogWriter(log_directory="test_logs")


print("\n--- Memulai Simulasi 1: Transaksi 101 (INSERT) ---")
TX_ID_101 = 101

print(f"Mencatat START untuk Transaksi {TX_ID_101}...")
log_start = log_writer.create_log_entry(TX_ID_101, ActionType.START)
log_writer.write_to_file(log_start)

laporan_insert = MockChangeReport(
    table_name="mahasiswa",
    old_data=None, # Karena INSERT, old_data kosong
    new_data={"nim": "13520001", "nama": "Budi"}
)
print(f"Mencatat WRITE (INSERT) untuk Transaksi {TX_ID_101}...")
log_write = log_writer.create_log_entry(TX_ID_101, ActionType.WRITE, laporan_insert)
log_writer.write_to_file(log_write)

print(f"Mencatat COMMIT untuk Transaksi {TX_ID_101}...")
log_commit = log_writer.create_log_entry(TX_ID_101, ActionType.COMMIT)
log_writer.write_to_file(log_commit)


print("\n--- Memulai Simulasi 2: Transaksi 102 (UPDATE -> ABORT) ---")
TX_ID_102 = 102

print(f"Mencatat START untuk Transaksi {TX_ID_102}...")
log_start_2 = log_writer.create_log_entry(TX_ID_102, ActionType.START)
log_writer.write_to_file(log_start_2)

laporan_update = MockChangeReport(
    table_name="mahasiswa",
    old_data={"nim": "13520001", "nama": "Budi"},
    new_data={"nim": "13520001", "nama": "Budi Hartono"}
)
print(f"Mencatat WRITE (UPDATE) untuk Transaksi {TX_ID_102}...")
log_write_2 = log_writer.create_log_entry(TX_ID_102, ActionType.WRITE, laporan_update)
log_writer.write_to_file(log_write_2)

print(f"Mencatat ABORT untuk Transaksi {TX_ID_102}...")
log_abort = log_writer.create_log_entry(TX_ID_102, ActionType.ABORT)
log_writer.write_to_file(log_abort)

print("\n--- Simulasi Selesai ---")
print(f"Silakan periksa file log di dalam folder: '{log_writer.log_directory}'")