from typing import Optional, Set, Dict, Any
from recovery_model import RecoverCriteria, LogEntry, MockQueryProcessor
from log_parser import LogParser

class RecoveryEngine:
    def __init__(self, log_directory: str = "test_logs", query_processor: MockQueryProcessor = None):
        self.log_parser = LogParser(log_directory=log_directory)
        self.query_processor = query_processor or MockQueryProcessor()

    def recover(self, criteria: RecoverCriteria) -> None:
        # Melakukan recovery secara backward dari entri terakhir hingga mencapai kriteria, dapat berupa timestamp atau transaction ID.
        # Recovery hanya dilakukan pada transaksi yang belum di-commit.
        committed: Set[int] = set()
        aborted: Set[int] = set()

        for entry in self.log_parser.iter_backward(criteria):
            tx = entry.transaction_id
            if entry.action == "COMMIT":
                committed.add(tx)
                print(f"[Recovery] Ditemukan COMMIT untuk transaksi {tx}; tidak akan meng-undo WRITE-nya")
                continue

            if entry.action == "ABORT":
                aborted.add(tx)
                print(f"[Recovery] Ditemukan ABORT untuk transaksi {tx}; WRITE-nya harus di-undo")
                continue

            if entry.action == "WRITE":
                # skip writes jika transaksi committed
                if tx in committed:
                    print(f"[Recovery] Melewatkan WRITE untuk transaksi {tx} yang sudah COMMIT")
                    continue

                # undo writes dari transaksi aborted
                if tx in aborted:
                    old = entry.old_data
                    print(f"[Recovery] Meng-undo WRITE untuk transaksi {tx} pada tabel {entry.table_name}")
                    self.query_processor.apply_undo(entry.table_name or "<unknown>", old, entry.new_data)
                else:
                    print(f"[Recovery] WRITE untuk transaksi {tx} ditemukan sebelum status akhir diketahui; dilewatkan untuk sementara")

        # Tambahkan logika write hasil rollback ke file log di sini