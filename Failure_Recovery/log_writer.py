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
    
    def clear_wal_before_oldest_transaction(self, ongoing_transactions: list):
        """
        Clear WAL entries that are no longer needed for recovery.
        Keep only entries for ongoing transactions and the most recent checkpoint.
        
        Args:
            ongoing_transactions: List of active transaction IDs
        """
        if not ongoing_transactions:
            print("[WAL Clear] No ongoing transactions, clearing entire WAL")
            self.clear_entire_wal()
            return
            
        # Convert to set for faster lookup
        ongoing_tx_set = set(ongoing_transactions)
        oldest_tx_id = min(ongoing_transactions)
        print(f"[WAL Clear] Oldest ongoing transaction: {oldest_tx_id}")
        print(f"[WAL Clear] Ongoing transactions: {sorted(ongoing_transactions)}")
        
        log_file = self._get_active_logfile()
        if not os.path.exists(log_file):
            print("[WAL Clear] No log file exists")
            return
            
        entries_to_keep = []
        oldest_tx_start_found = False
        latest_checkpoint = None
        
        # Read all entries
        with open(log_file, 'r') as f:
            lines = f.readlines()
        
        # Find the most recent checkpoint first
        for line in lines:
            try:
                entry = json.loads(line.strip())
                if entry.get('type') == 'checkpoint':
                    latest_checkpoint = line
            except json.JSONDecodeError:
                continue
        
        # Process entries to keep only relevant ones
        for line in lines:
            try:
                entry = json.loads(line.strip())
                tx_id = entry.get('transaction_id')
                action = entry.get('action')
                entry_type = entry.get('type')
                
                # Always keep the most recent checkpoint
                if entry_type == 'checkpoint' and line == latest_checkpoint:
                    entries_to_keep.append(line)
                    print(f"[WAL Clear] Keeping most recent checkpoint")
                    continue
                
                # Check if this is the START of oldest ongoing transaction
                if (tx_id == oldest_tx_id and action == 'start'):
                    oldest_tx_start_found = True
                    print(f"[WAL Clear] Found START of oldest TX {oldest_tx_id}")
                
                # Keep entries only if they belong to ongoing transactions
                # and we've found the oldest transaction start
                if oldest_tx_start_found and tx_id in ongoing_tx_set:
                    entries_to_keep.append(line)
                    
            except json.JSONDecodeError:
                # Skip malformed entries
                continue
        
        # Write back only the entries we want to keep
        with open(log_file, 'w') as f:
            f.writelines(entries_to_keep)
            
        cleared_count = len(lines) - len(entries_to_keep)
        print(f"[WAL Clear] Cleared {cleared_count} entries")
        print(f"[WAL Clear] Kept {len(entries_to_keep)} entries (checkpoint + ongoing transactions)")
        
        # Show what we kept for debugging
        print("[WAL Clear] Kept entries:")
        for i, line in enumerate(entries_to_keep):
            try:
                entry = json.loads(line.strip())
                tx_id = entry.get('transaction_id', 'N/A')
                action = entry.get('action', entry.get('type', 'unknown'))
                print(f"  {i+1}. TX {tx_id}: {action}")
            except:
                print(f"  {i+1}. [Malformed entry]")
    
    def clear_entire_wal(self):
        """Clear the entire WAL file"""
        log_file = self._get_active_logfile()
        if os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write('')  # Empty the file
            print("[WAL Clear] Entire WAL cleared")
        else:
            print("[WAL Clear] No WAL file to clear")