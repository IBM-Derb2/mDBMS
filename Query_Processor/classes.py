from datetime import datetime
import re
from dataclasses import dataclass, field
from typing import List, Any, Optional, Union

@dataclass
class Rows:
    # Menampung hasil data dari eksekusi query.
    data: List[dict] = field(default_factory=list)

@dataclass
class ExecutionResult:
    # Object hasil eksekusi query yang akan dicatat oleh Failure Recovery Manager dan dikembalikan ke User
    transaction_id: int
    query: str
    timestamp: datetime
    message: str
    rows_count: int = 0
    data: Optional[Rows] = None


class QueryProcessor:
    # Komponen utama
    def __init__(self, optimizer, storage_manager, cc_manager, fr_manager):
        self.optimizer = optimizer
        self.storage_manager = storage_manager
        self.cc_manager = cc_manager
        self.fr_manager = fr_manager
        self.current_transaction_id = None

    def execute_query(self, query: str) -> ExecutionResult:
        # Menerima string query, memprosesnya, dan mengembalikan ExecutionResult.
        
        # Validasi input
        if not query or not query.strip():
            return ExecutionResult(
                transaction_id=self.current_transaction_id or 0,
                query=query or "",
                timestamp=datetime.now(),
                message="Error: Empty query",
                rows_count=0
            )
        
        print(f"\n[QP] Received query: '{query}'")
        query_upper = query.upper().strip()

        try:
            # Transaction
            if query_upper.startswith("BEGIN TRANSACTION") or query_upper == "BEGIN":
                return self._handle_begin_transaction(query)
            
            if query_upper.startswith("COMMIT"):
                return self._handle_commit(query)
            
            if query_upper.startswith("ROLLBACK"):
                return self._handle_rollback(query)

            # DML/DDL
            if self.current_transaction_id is None:
                # Auto-begin transaction untuk single statement
                print("[QP] No active transaction. Auto-beginning new transaction.")
                self._handle_begin_transaction("BEGIN TRANSACTION")

            # Parsing untuk menentukan jenis query
            if query_upper.startswith("SELECT"):
                result = self._handle_select(query)
            elif query_upper.startswith("UPDATE"):
                result = self._handle_update(query)
            elif query_upper.startswith("DELETE"):
                result = self._handle_delete(query)
            elif query_upper.startswith("INSERT"):
                result = self._handle_insert(query)
            elif query_upper.startswith("CREATE TABLE"):
                result = self._handle_create_table(query)
            elif query_upper.startswith("DROP TABLE"):
                result = self._handle_drop_table(query)
            else:
                raise ValueError(f"Unsupported query type: {query_upper.split()[0] if query_upper else 'UNKNOWN'}")

            # Jika sukses, log eksekusi
            self.fr_manager.write_log(result)
            return result

        except Exception as e:
            print(f"[QP] Error executing query: {e}")
            # Rollback transaction on error
            error_result = ExecutionResult(
                transaction_id=self.current_transaction_id or 0,
                query=query,
                timestamp=datetime.now(),
                message=f"Error: {str(e)}",
                rows_count=0
            )
            
            # Log error dan rollback jika ada transaction aktif
            if self.current_transaction_id is not None:
                print(f"[QP] Rolling back transaction {self.current_transaction_id} due to error.")
                self.cc_manager.abort_transaction(self.current_transaction_id, "Error occurred")
                self.fr_manager.write_log(error_result)
                self.current_transaction_id = None
            
            return error_result

    def _handle_begin_transaction(self, query):
        self.current_transaction_id = self.cc_manager.begin_transaction()
        print(f"[QP] Handled BEGIN TRANSACTION. New TID: {self.current_transaction_id}")
        return ExecutionResult(
            transaction_id=self.current_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message="Transaction started."
        )

    def _handle_commit(self, query):
        if self.current_transaction_id is None:
            raise ValueError("No active transaction to commit.")
        
        self.cc_manager.commit_transaction(self.current_transaction_id)
        print(f"[QP] Handled COMMIT for TID: {self.current_transaction_id}")
        
        result = ExecutionResult(
            transaction_id=self.current_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message="Transaction committed."
        )
        self.fr_manager.write_log(result) # Log commit
        
        self.current_transaction_id = None # End local transaction
        return result
    
    def _handle_rollback(self, query) :
        if self.current_transaction_id is None:
            raise ValueError("No active transaction to rollback.")
        
        print(f"[QP] Handling ROLLBACK for TID: {self.current_transaction_id}")
        self.cc_manager.abort_transaction(self.current_transaction_id, "User rollback")
        
        result = ExecutionResult(
            transaction_id=self.current_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message="Transaction rolled back."
        )
        self.fr_manager.write_log(result) # Log rollback
        
        self.current_transaction_id = None # End local transaction
        return result

    def _extract_table_name(self, query: str) -> str:
        # Helper method untuk mengekstrak nama tabel dari query.
        # Digunakan untuk validasi concurrency control.
        query_upper = query.upper().strip()
        
        # Pattern untuk berbagai jenis query
        patterns = [
            r'FROM\s+(\w+)',        # SELECT ... FROM table
            r'UPDATE\s+(\w+)',      # UPDATE table SET ...
            r'DELETE\s+FROM\s+(\w+)', # DELETE FROM table
            r'INSERT\s+INTO\s+(\w+)', # INSERT INTO table
            r'CREATE\s+TABLE\s+(\w+)', # CREATE TABLE table
            r'DROP\s+TABLE\s+(\w+)'    # DROP TABLE table
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query_upper)
            if match:
                return match.group(1).lower()
        
        return "unknown_table"  # Fallback
    
    def _execute_plan(self, query, parsed_query):
        # Helper DML
        
        # Dapatkan query plan
        query_plan = self.optimizer.optimize_query(parsed_query)
        # print(f"[QP] Got optimized plan: {query_plan.plan_details}")

        # Validasi objek ke Concurrency Control
        table_name = self._extract_table_name(query)
        action = "read"
        
        self.cc_manager.log_object(table_name, self.current_transaction_id, action)
        response = self.cc_manager.validate_object(
            table_name, self.current_transaction_id, action
        )
        print(f"[QP] CCM validation response: {response.allowed}")

        if not response.allowed:
            raise Exception("Transaction aborted by Concurrency Control Manager.")

        # Ambil data dari Storage Manager
        data_retrieval_request = f"DataRetrieval for: {query_plan.query}"
        rows = self.storage_manager.read_block(data_retrieval_request)
        print(f"[QP] Fetched data from Storage Manager: {rows.data}")

        # Lakukan manipulasi (JOIN, ORDER BY, etc.)
        processed_data = self._process_query_data(query, rows)
        print(f"[QP] Data manipulation complete. Final rows: {len(processed_data.data)}")
        
        # Kembalikan ExecutionResult
        message = "Query executed successfully."
        return ExecutionResult(
            transaction_id=self.current_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message=message,
            rows_count=len(processed_data.data),
            data=processed_data
        )

    def _process_query_data(self, query: str, rows: Any) -> Rows:
        # Process query data for ORDER BY, LIMIT, etc. demonstrasi.
        query_upper = query.upper()
        result_data = rows.data.copy() if hasattr(rows, 'data') else []
        
        # Handle ORDER BY
        order_by_match = re.search(r'ORDER\s+BY\s+(\w+)(\s+DESC)?', query_upper)
        if order_by_match and result_data:
            column = order_by_match.group(1).lower()
            is_desc = order_by_match.group(2) is not None
            
            # Sort data jika kolom ada
            if result_data and column in result_data[0]:
                result_data = sorted(result_data, key=lambda x: x.get(column, ''), reverse=is_desc)
                print(f"[QP] Applied ORDER BY {column} {'DESC' if is_desc else 'ASC'}")
        
        # Handle LIMIT
        limit_match = re.search(r'LIMIT\s+(\d+)', query_upper)
        if limit_match:
            limit = int(limit_match.group(1))
            result_data = result_data[:limit]
            print(f"[QP] Applied LIMIT {limit}")
        
        return Rows(data=result_data)

    def _handle_select(self, query):
        print("[QP] Handling SELECT/JOIN query...")
        # Kirim ke Query Optimizer
        parsed_query = self.optimizer.parse_query(query)
        
        # Lanjutkan eksekusi
        return self._execute_plan(query, parsed_query)

    def _handle_update(self, query):
        print("[QP] Handling UPDATE query...")
        parsed_query = self.optimizer.parse_query(query)
        query_plan = self.optimizer.optimize_query(parsed_query)
        
        table_name = self._extract_table_name(query)
        self.cc_manager.log_object(table_name, self.current_transaction_id, "write")
        response = self.cc_manager.validate_object(
            table_name, self.current_transaction_id, "write"
        )
        if not response.allowed:
            raise Exception("Transaction aborted by Concurrency Control Manager.")
            
        data_write_request = f"DataWrite for: {query_plan.query}"
        affected_rows = self.storage_manager.write_block(data_write_request)
        
        message = f"UPDATE executed. {affected_rows} rows affected."
        return ExecutionResult(
            transaction_id=self.current_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message=message,
            rows_count=affected_rows
        )

    def _handle_delete(self, query):
        print("[QP] Handling DELETE query ...")
        parsed_query = self.optimizer.parse_query(query)
        query_plan = self.optimizer.optimize_query(parsed_query)

        table_name = self._extract_table_name(query)
        self.cc_manager.log_object(table_name, self.current_transaction_id, "write")
        response = self.cc_manager.validate_object(
            table_name, self.current_transaction_id, "write"
        )
        if not response.allowed:
            raise Exception("Transaction aborted by Concurrency Control Manager.")
            
        data_deletion_request = f"DataDeletion for: {query_plan.query}"
        affected_rows = self.storage_manager.delete_block(data_deletion_request)
        
        message = f"DELETE executed. {affected_rows} rows affected."
        return ExecutionResult(
            transaction_id=self.current_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message=message,
            rows_count=affected_rows
        )

    def _handle_insert(self, query):
        print("[QP] Handling INSERT query...")
        parsed_query = self.optimizer.parse_query(query)
        query_plan = self.optimizer.optimize_query(parsed_query)
        
        table_name = self._extract_table_name(query)
        self.cc_manager.log_object(table_name, self.current_transaction_id, "write")
        response = self.cc_manager.validate_object(
            table_name, self.current_transaction_id, "write"
        )
        if not response.allowed:
            raise Exception("Transaction aborted by Concurrency Control Manager.")
            
        data_write_request = f"DataWrite for: {query_plan.query}"
        affected_rows = self.storage_manager.write_block(data_write_request)
        
        message = f"INSERT executed. {affected_rows} rows affected."
        return ExecutionResult(
            transaction_id=self.current_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message=message,
            rows_count=affected_rows
        )

    def _handle_create_table(self, query):
        print("[QP] Handling CREATE TABLE query...")
        parsed_query = self.optimizer.parse_query(query)
        query_plan = self.optimizer.optimize_query(parsed_query)
        
        table_name = self._extract_table_name(query)
        self.cc_manager.log_object(table_name, self.current_transaction_id, "write")
        response = self.cc_manager.validate_object(
            table_name, self.current_transaction_id, "write"
        )
        if not response.allowed:
            raise Exception("Transaction aborted by Concurrency Control Manager.")
        
        # DDL memanggil metode di Storage Manager
        # untuk mock, gunakan write_block
        data_write_request = f"DDL_CREATE for: {query_plan.query}"
        affected_rows = self.storage_manager.write_block(data_write_request) # Asumsi 0
        
        message = "CREATE TABLE executed."
        return ExecutionResult(
            transaction_id=self.current_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message=message,
            rows_count=affected_rows
        )

    def _handle_drop_table(self, query):
        print("[QP] Handling DROP TABLE query...")
        parsed_query = self.optimizer.parse_query(query)
        query_plan = self.optimizer.optimize_query(parsed_query)
        
        table_name = self._extract_table_name(query)
        self.cc_manager.log_object(table_name, self.current_transaction_id, "write")
        response = self.cc_manager.validate_object(
            table_name, self.current_transaction_id, "write"
        )
        if not response.allowed:
            raise Exception("Transaction aborted by Concurrency Control Manager.")
            
        data_deletion_request = f"DDL_DROP for: {query_plan.query}"
        affected_rows = self.storage_manager.delete_block(data_deletion_request) # Asumsi 0
        
        message = "DROP TABLE executed."
        return ExecutionResult(
            transaction_id=self.current_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message=message,
            rows_count=affected_rows
        )