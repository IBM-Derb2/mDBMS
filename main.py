 
from Query_Processor.classes import QueryProcessor
from Query_Optimizer.optimization_engine import OptimizationEngine
from Concurrency_Control_Manager.classes import ConcurrencyControlManager
from Storage_Manager.classes import StorageEngine
from Failure_Recovery.classes import FailureRecovery

def main():
    print("--- mini Database Management System (mDBMS) ---")
    print("Initializing components...")

    optimizer = OptimizationEngine()
    storage = StorageEngine()
    cc_manager = ConcurrencyControlManager()
    fr_manager = FailureRecovery()

    qp = QueryProcessor(
        optimizer=optimizer,
        storage_manager=storage,
        cc_manager=cc_manager,
        fr_manager=fr_manager
    )

    print("\n[mDBMS] Ready. Type your SQL query or 'exit' to quit.")
    
    while True:
        try:
            query = input("mDBMS> ")
            if query.lower() == 'exit':
                print("[mDBMS] Shutting down.")
                break
            
            if not query:
                continue

            result = qp.execute_query(query)

            print("\n--- Query Result ---")
            print(f"  Message: {result.message}")
            print(f"  TID: {result.transaction_id}")
            print(f"  Rows Affected/Returned: {result.rows_count}")
            if result.data and result.data.data:
                print("  Data:")
                for row in result.data.data:
                    print(f"    {row}")
            print("--------------------\n")

        except Exception as e:
            print(f"[mDBMS Error] An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()