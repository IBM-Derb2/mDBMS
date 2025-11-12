import os
import json
from datetime import datetime
from typing import Optional, Iterator, List, Dict, Any

from recovery_model import RecoverCriteria, LogEntry

def iter_file_backward(path: str, buf_size: int = 4096) -> Iterator[str]:
    # Fungsi individual untuk membaca baris dari file log dari akhir ke awal (tanpa loading seluruh file)
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_pos = f.tell()
        remainder = b""
        while file_pos > 0:
            read_size = min(buf_size, file_pos)
            file_pos -= read_size
            f.seek(file_pos)
            chunk = f.read(read_size)
            parts = chunk + remainder
            lines = parts.split(b"\n")
            remainder = lines[0]
            for line in reversed(lines[1:]):
                yield line.decode("utf-8", "replace")
        if remainder:
            yield remainder.decode("utf-8", "replace")

class LogParser:
    # Parsing file log dari directory yang ditentukan, membaca entri log terbaru -> terlama, baris bawah -> atas
    def __init__(self, log_directory: str = "test_logs"):
        self.log_directory = log_directory

    def _sorted_log_files_desc(self) -> List[str]:
        # mengurutkan berdasarkan format nama dengan timestamp: "logfile_[date]_[time].log"
        files = [f for f in os.listdir(self.log_directory) if f.startswith("logfile_")]
        files.sort(reverse=True)
        return [os.path.join(self.log_directory, f) for f in files]

    def _parse_line(self, line: str) -> Optional[LogEntry]:
        try:
            d: Dict[str, Any] = json.loads(line)
            ts = datetime.fromisoformat(d["timestamp"]) if "timestamp" in d else datetime.now()
            return LogEntry(
                timestamp=ts,
                transaction_id=int(d.get("transaction_id", -1)),
                action=d.get("action"),
                table_name=d.get("table_name"),
                old_data=d.get("old_data"),
                new_data=d.get("new_data"),
                raw_log=d,
            )
        except Exception:
            return None

    def iter_backward(self, criteria: Optional[RecoverCriteria] = None) -> Iterator[LogEntry]:
        # iterasi entri log saat recovery hingga mencapai RecoveryCriteria
        if criteria is None:
            criteria = RecoverCriteria()

        for filepath in self._sorted_log_files_desc():
            for line in iter_file_backward(filepath):
                entry = self._parse_line(line.strip())
                if not entry:
                    continue

                # timestamp criteria, stop jika entry lebih tua dari criteria
                if criteria.timestamp and entry.timestamp < criteria.timestamp:
                    return

                yield entry

                # transaction id criteria, stop ketika mencapai awal dari transaksi dengan id tsb
                if criteria.transaction_id and entry.transaction_id == criteria.transaction_id and entry.action == "START":
                    return