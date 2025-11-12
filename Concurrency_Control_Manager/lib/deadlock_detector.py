from .transaction_model import TransactionManager


class DeadlockDetector:

    def __init__(self, tx_manager: TransactionManager):
        self.tx_manager = tx_manager

    def check_and_resolve(self, abort_callback) -> bool:
        cycle = self.tx_manager.detect_deadlock()

        if cycle:
            youngest_tx_id = max(cycle)
            abort_callback(youngest_tx_id, "Deadlock victim")
            return True

        return False
