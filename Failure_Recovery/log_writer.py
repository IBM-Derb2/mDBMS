import os
import json
from datetime import datetime
from log_config import ActionType, MockChangeReport

class LogWriter:
    def __init__(self, log_directory: str = "logs"):
        # saat class ini dibuat, classnya akan ngecek apakah folder logs ada? klo gk ada dibuat folder baru
        self.log_directory = log_directory
        self.active_logfile = None
        os.makedirs(self.log_directory, exist_ok=True)
    
    def _get_active_logfile(self) -> str:
        # mencari file log yang active
        # jika takde, buat file baru based on datetime
        if self.active_logfile is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.active_logfile = os.path.join(self.log_directory, f"logfile_{timestamp}.log")
            print(f"[LogWriter] File log baru telah dibuat: {self.active_logfile}")
        
        return self.active_logfile
    
    def create_log_entry(self, transaction_id: int, action: ActionType, change_report: MockChangeReport = None) -> str:
        # mengubah data mntah jadi format log (json string)
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "transaction_id": transaction_id,
            "action" :action.name
        }
        # jika ini adalah aksi wite, tambahin detail perubahannya
        if action == ActionType.WRITE and change_report:
            log_data["table_name"] = change_report.table_name
            log_data["pk_value"] = change_report.pk_value
            log_data["old_data"] = change_report.old_data
            log_data["new_data"] = change_report.new_data
        # ubah dict py jadi string json
        return json.dumps(log_data)

    def write_to_file(self, log_entry_string: str):
            # nulis string log ke file di disk.
            # 1. dapetin nama file
            filepath = self._get_active_logfile()
            
            # 2. tulis log baru di baris paling bawah (mode "a" artinya append)
            try:
                with open(filepath, "a") as f:
                    f.write(log_entry_string + "\n")
            except Exception as e:
                print(f"[LogWriter] GAGAL menulis ke file log: {e}")