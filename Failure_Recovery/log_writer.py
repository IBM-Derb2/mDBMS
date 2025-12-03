import os
import json
from datetime import datetime
from typing import Any, List
from log_config import WalType, WalAction

class LogWriter:
    def __init__(self, log_directory: str = "wal_logs"):
        self.log_directory = log_directory
        os.makedirs(self.log_directory, exist_ok=True)
        self.current_log_file = self._get_new_log_file()
        self.active_logfile = None

    def _get_active_logfile(self) -> str:
        # mencari file log yang active
        # jika takde, buat file baru based on datetime
        if self.active_logfile is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.active_logfile = os.path.join(self.log_directory, f"logfile_{timestamp}.log")
            print(f"[LogWriter] File log baru telah dibuat: {self.active_logfile}")
        
        return self.active_logfile
    
    def _get_new_log_file(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logfile_{timestamp}.log"
        filepath = os.path.join(self.log_directory, filename)
        print(f"[LogWriter] File log baru telah dibuat: {filepath}")
        return filepath

    def write_to_file(self, content: str):
        """Menulis string mentah ke file (low-level)"""
        with open(self.current_log_file, "a") as f:
            f.write(content + "\n")
            
    def log_lifecycle(self, tx_id: int, action: WalAction):
        """Mencatat START, COMMIT, ABORT"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.EXECUTION.value,
            "action": action.value,
            "transaction_id": tx_id
        }
        self.write_to_file(json.dumps(entry))

    def log_operation(self, tx_id: int, table: str, pk: Any, 
                      old_data: dict, new_data: dict):
        """Mencatat INSERT, UPDATE, DELETE (Otomatis deteksi aksi)"""
        
        # Deteksi Action berdasarkan data
        if old_data is None and new_data is not None:
            action_str = WalAction.INSERT.value
        elif old_data is not None and new_data is None:
            action_str = WalAction.DELETE.value
        elif old_data is not None and new_data is not None:
            action_str = WalAction.UPDATE.value
        else:
            # Case aneh (misal None -> None), skip atau catat warning
            return 

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.EXECUTION.value,
            "action": action_str,
            "transaction_id": tx_id,
            "tablename": table,
            "pk_value": pk,
            "record_before": old_data,
            "record_after": new_data
        }
        self.write_to_file(json.dumps(entry))

    def log_checkpoint(self, ongoing_transactions: List[int]):
        """Mencatat Checkpoint"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.CHECKPOINT.value,
            "ongoing_transactions": ongoing_transactions
        }
        self.write_to_file(json.dumps(entry))
        
    def log_compensation(self, tx_id: int, original_action: str, table: str, pk: Any, restored_data: dict):
        """Mencatat CLR (Compensation Log Record) saat Undo"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": WalType.EXECUTION.value,
            "action": "clr",
            "original_action": original_action,
            "transaction_id": tx_id,
            "tablename": table,
            "pk_value": pk,
            "record_before": None,
            "record_after": restored_data
        }
        self.write_to_file(json.dumps(entry))
    
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