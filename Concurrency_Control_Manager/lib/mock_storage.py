class MockStorageManager:
    """
    Mock Storage Manager for testing rollback functionality.
    This will be replaced with actual Storage Manager implementation later.
    """

    def __init__(self):
        self.write_operations = []

    def write_block(self, *args, **kwargs):
        """
        Mock write operation to simulate rollback to storage.
        Accepts flexible arguments to avoid errors during actual calls.
        """
        operation_info = {
            "args": args,
            "kwargs": kwargs
        }
        self.write_operations.append(operation_info)
        
        # Print evidence of rollback operation
        print(f"[MockStorage] ROLLBACK WRITE: {operation_info}")
        
        # If old_value is passed, show it explicitly
        if "old_value" in kwargs:
            print(f"[MockStorage] Restoring value: {kwargs['old_value']}")

    def get_write_history(self):
        """Return history of all write operations."""
        return self.write_operations

    def clear_history(self):
        """Clear write operation history."""
        self.write_operations.clear()