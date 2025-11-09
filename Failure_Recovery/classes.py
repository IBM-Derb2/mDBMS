from typing import Any

class FailureRecovery:
    
    def __init__(self):
        self.log_buffer = []
        print("[FRM Mock] Write-Ahead Log buffer initialized.")

    def write_log(self, info: Any):
        print(f"[FRM Mock] Writing to WAL: (TID: {info.transaction_id}) {info.message}")
        self.log_buffer.append(info)

    def save_checkpoint(self):
        print("[FRM Mock] Saving checkpoint... Flushing WAL to disk.")
        self.log_buffer.clear()

    def recover(self, criteria: Any):
        print(f"[FRM Mock] Recovering database using criteria: {criteria}")
