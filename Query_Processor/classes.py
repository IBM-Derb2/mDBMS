from datetime import datetime
import time
from dataclasses import dataclass
from typing import List, Optional, Union

from globalsy.constants.query_types import QueryTypes
from globalsy.classes.rows import Rows
from Storage_Manager.utils import Condition, DataRetrieval, DataWrite, DataDeletion


@dataclass
class ClientSession:
    """Per-client transaction session state"""
    current_transaction_id: Optional[str] = None
    multiple_transaction: bool = False
    explicit_transaction: bool = False
    result_storage: List = None
    query_storage: List = None
    transaction_failed: bool = False

    def __post_init__(self):
        if self.result_storage is None:
            self.result_storage = []
        if self.query_storage is None:
            self.query_storage = []


@dataclass
class ExecutionResult:
    # Can be int (legacy) or str (IP-timestamp format)
    transaction_id: Union[int, str]
    query: str
    timestamp: datetime
    message: str
    rows_count: int = 0
    data: Optional[Rows] = None


class QueryProcessor:

    CCM_RETRY_MAX = 5
    CCM_RETRY_DELAY = 0.1
    DEBUG = True  # Set to True to print full tracebacks

    def __init__(self, optimizer, storage_manager, cc_manager):
        self.optimizer = optimizer
        self.storage_manager = storage_manager
        self.cc_manager = cc_manager

        # Per-client session tracking: key = "ip:port", value = ClientSession
        self.client_sessions = {}

        # Legacy fields kept for backward compatibility (non-client scenarios)
        self.current_transaction_id = None
        self.multiple_transaction = False
        self.explicit_transaction = False
        self.result_storage = []
        self.query_storage = []
        self.transaction_failed = False

    def _get_client_session(self, client_address: tuple = None) -> ClientSession:
        """Get or create a session for the given client address"""
        if not client_address:
            # Legacy mode: use instance variables
            return None

        client_key = f"{client_address[0]}:{client_address[1]}"
        if client_key not in self.client_sessions:
            self.client_sessions[client_key] = ClientSession()
        return self.client_sessions[client_key]

    def _cleanup_client_session(self, client_address: tuple):
        """Remove client session after transaction ends"""
        if client_address:
            client_key = f"{client_address[0]}:{client_address[1]}"
            if client_key in self.client_sessions:
                # Only cleanup if no active transaction
                session = self.client_sessions[client_key]
                if not session.multiple_transaction:
                    del self.client_sessions[client_key]

    # for anyone who still don't know, this is the entry point ...

    def execute_query(self, query: str, client_address: tuple = None) -> List[ExecutionResult]:
        # Get client session or use legacy mode
        session = self._get_client_session(client_address)

        # Use session state if available, otherwise use instance state (legacy)
        if session:
            current_transaction_id = session.current_transaction_id
            multiple_transaction = session.multiple_transaction
            explicit_transaction = session.explicit_transaction
            query_storage = session.query_storage
            transaction_failed = session.transaction_failed
        else:
            current_transaction_id = self.current_transaction_id
            multiple_transaction = self.multiple_transaction
            explicit_transaction = self.explicit_transaction
            query_storage = self.query_storage
            transaction_failed = self.transaction_failed

        query = query.strip()

        if not query:
            return [self._create_error_result("", "Empty query")]

        query_upper = query.upper().strip()

        if query_upper.upper == "BEGIN" or query_upper == "BEGIN TRANSACTION":
            return [self._handle_begin_transaction(query, client_address)]

        if query_upper == "COMMIT":
            return self._handle_commit(query, client_address)

        if query_upper == "ROLLBACK" or query_upper == "ABORT":
            return [self._handle_rollback(query, client_address)]

        if query_upper.startswith("SET CONCURRENCY") and query_upper.endswith(";"):
            return [self._handle_set_concurrency(query, client_address)]

        if explicit_transaction:
            # in failed state
            if transaction_failed:
                return [self._create_error_result(
                    query,
                    f"Transaction {current_transaction_id} has failed. Please ROLLBACK before proceeding."
                )]

            # validate query syntax even in transaction mode
            if not query.endswith(";"):
                if session:
                    session.transaction_failed = True
                else:
                    self.transaction_failed = True
                error_result = self._create_error_result(
                    query, "Query must end with a semicolon. Transaction marked as failed. Please ROLLBACK.")
                print(
                    f"[QP] Query error in transaction {current_transaction_id} - transaction marked as failed")
                return [error_result]

            try:
                parsed_query = self.optimizer.parse_query(query)
                optimized_query = self.optimizer.optimize_query(parsed_query)

                query_upper = query.strip().upper()
                is_select_query = query_upper.startswith("SELECT")

                if is_select_query:
                    print(
                        f"[QP] Executing SELECT in transaction {current_transaction_id}")
                    try:
                        self.current_transaction_id = current_transaction_id

                        result = self._process_node(optimized_query.query_tree)
                        message = result.message if result.message else f"Query returned {result.rows_count} row(s)"

                        # track query for commit count
                        query_storage.append(query)

                        return [ExecutionResult(
                            data=result,
                            message=message,
                            query=query,
                            transaction_id=current_transaction_id,
                            timestamp=datetime.now(),
                            rows_count=result.rows_count if result else 0
                        )]
                    except Exception as exec_error:
                        print(f"[QP] SELECT execution error: {exec_error}")
                        import traceback
                        traceback.print_exc()
                        if session:
                            session.transaction_failed = True
                        else:
                            self.transaction_failed = True
                        error_result = self._create_error_result(
                            query, f"Execution error: {str(exec_error)}. Transaction marked as failed. Please ROLLBACK.")
                        return [error_result]
                else:
                    # write operations (INSERT, UPDATE, DELETE) execute immediately, not committed to disk
                    print(
                        f"[QP] Executing write operation in transaction {current_transaction_id}")
                    try:
                        self.current_transaction_id = current_transaction_id

                        result = self._process_node(optimized_query.query_tree)
                        message = result.message if result.message else f"Query affected {result.rows_count} row(s)"

                        # track query for commit count
                        query_storage.append(query)

                        # return result immediately (data in buffer, pending commit to disk)
                        return [ExecutionResult(
                            data=result,
                            message=f"{message} (pending commit)",
                            query=query,
                            transaction_id=current_transaction_id,
                            timestamp=datetime.now(),
                            rows_count=result.rows_count if result else 0
                        )]
                    except Exception as exec_error:
                        print(
                            f"[QP] Write operation execution error: {exec_error}")
                        if self.DEBUG:
                            import traceback
                            traceback.print_exc()
                        if session:
                            session.transaction_failed = True
                        else:
                            self.transaction_failed = True
                        error_result = self._create_error_result(
                            query, f"Execution error: {str(exec_error)}. Transaction marked as failed. Please ROLLBACK.")
                        return [error_result]
            except Exception as e:
                error_msg = str(e)
                print(
                    f"[QP] Query parsing failed in transaction {current_transaction_id}")
                print(f"[QP] Error: {error_msg}")
                if self.DEBUG:
                    import traceback
                    traceback.print_exc()
                if session:
                    session.transaction_failed = True
                else:
                    self.transaction_failed = True
                error_result = self._create_error_result(
                    query, f"{error_msg}. Transaction marked as failed. Please ROLLBACK.")
                return [error_result]

        if not query.endswith(";"):
            return [self._create_error_result(query, "Query must end with a semicolon")]

        # Get session for auto-commit mode to properly clean up after commit
        session = self._get_client_session(client_address)

        # Check if client has an active transaction (use session if available)
        current_tx_id = session.current_transaction_id if session else self.current_transaction_id

        try:
            if current_tx_id is None:
                self._handle_begin_transaction(
                    "BEGIN TRANSACTION", client_address)

            parsed_query = self.optimizer.parse_query(query)
            optimized_query = self.optimizer.optimize_query(parsed_query)
            result = self._process_node(optimized_query.query_tree)

            # Not mask failures with generic "success" message
            message = result.message if result.message else f"Query returned {result.rows_count} row(s)"

            execution_result = ExecutionResult(
                data=result,
                message=message,
                query=query,
                transaction_id=self.current_transaction_id,
                timestamp=datetime.now(),
                rows_count=result.rows_count if result else 0
            )

            self._commit(session)
            return [execution_result]

        except Exception as e:
            error_msg = str(e)
            print(f"[QP] Error: {error_msg}")
            if self.DEBUG:
                import traceback
                traceback.print_exc()
            if self.current_transaction_id is not None:
                self._rollback(session)

            return [self._create_error_result(query, error_msg)]

    # tektokan sama CCM, transactions

    def _handle_begin_transaction(self, query: str, client_address: tuple = None) -> ExecutionResult:
        # Get or create client session
        session = self._get_client_session(client_address)

        # Use session state if available, otherwise use instance state (legacy)
        if session:
            current_transaction_id = session.current_transaction_id
            multiple_transaction = session.multiple_transaction
        else:
            current_transaction_id = self.current_transaction_id
            multiple_transaction = self.multiple_transaction

        # Check if a transaction is already active for this client
        if multiple_transaction and current_transaction_id is not None:
            return ExecutionResult(
                transaction_id=current_transaction_id,
                query=query,
                timestamp=datetime.now(),
                message=f"Error: Transaction {current_transaction_id} is already active. COMMIT or ROLLBACK first."
            )

        # Extract client IP and port from address tuple
        if client_address:
            # For real client connections
            client_ip = client_address[0]
            client_port = client_address[1]
        else:
            # For unittests and non-client scenarios
            client_ip = None
            client_port = None

        new_transaction_id = self.cc_manager.begin_transaction(
            client_ip, client_port)

        # Update session or instance state
        if session:
            session.current_transaction_id = new_transaction_id
            session.multiple_transaction = True
            session.explicit_transaction = True
            self.current_transaction_id = new_transaction_id
        else:
            self.current_transaction_id = new_transaction_id
            self.multiple_transaction = True
            self.explicit_transaction = True

        print(
            f"[QP] Handled BEGIN TRANSACTION. New TID: {new_transaction_id}")
        return ExecutionResult(
            transaction_id=new_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message="Transaction started. Add queries and type COMMIT to execute, or ROLLBACK to cancel."
        )

    def _handle_commit(self, query: str, client_address: tuple = None) -> List[ExecutionResult]:
        # Get client session
        session = self._get_client_session(client_address)

        # Use session state if available, otherwise use instance state
        if session:
            current_transaction_id = session.current_transaction_id
            multiple_transaction = session.multiple_transaction
            transaction_failed = session.transaction_failed
            query_storage = session.query_storage
        else:
            current_transaction_id = self.current_transaction_id
            multiple_transaction = self.multiple_transaction
            transaction_failed = self.transaction_failed
            query_storage = self.query_storage

        # Check if there's an active explicit transaction
        if not multiple_transaction and current_transaction_id is None:
            return [ExecutionResult(
                transaction_id=0,
                query=query,
                timestamp=datetime.now(),
                message="Error: No active transaction to commit.",
                rows_count=0
            )]

        # Check if transaction is in failed state
        if transaction_failed:
            return [self._create_error_result(
                query,
                f"Cannot COMMIT - transaction {current_transaction_id} has failed. Please ROLLBACK."
            )]

        # Count queries executed in this transaction (from query_storage)
        query_count = len(query_storage)

        # Save TID before commit clears it
        committed_tid = current_transaction_id

        # Commit will flush buffer to disk (queries already executed)
        self._commit(session)

        # Return commit summary with query count
        return [ExecutionResult(
            transaction_id=committed_tid,
            query=query,
            timestamp=datetime.now(),
            message=f"Transaction committed successfully. {query_count} {'query' if query_count == 1 else 'queries'} executed.",
            rows_count=0
        )]

    def _handle_rollback(self, query: str, client_address: tuple = None) -> ExecutionResult:
        # Get client session
        session = self._get_client_session(client_address)

        # Use session state if available, otherwise use instance state
        if session:
            current_transaction_id = session.current_transaction_id
            multiple_transaction = session.multiple_transaction
            query_storage = session.query_storage
        else:
            current_transaction_id = self.current_transaction_id
            multiple_transaction = self.multiple_transaction
            query_storage = self.query_storage

        # Check if there's an active transaction to rollback
        if not multiple_transaction and current_transaction_id is None:
            return ExecutionResult(
                transaction_id=0,
                query=query,
                timestamp=datetime.now(),
                message="Error: No active transaction to rollback."
            )

        tid = current_transaction_id
        query_count = len(query_storage) if query_storage else 0

        if current_transaction_id is not None:
            self.cc_manager.abort_transaction(
                current_transaction_id, "User requested")

        self._reset_transaction_state(session)

        message = f"Transaction rolled back. {query_count} pending {'query' if query_count == 1 else 'queries'} discarded." if query_count > 0 else "Transaction rolled back."

        return ExecutionResult(
            transaction_id=tid if tid else 0,
            query=query,
            timestamp=datetime.now(),
            message=message
        )

    def _handle_set_concurrency(self, query: str, client_address: tuple = None) -> ExecutionResult:

        # SET CONCURRENCY TO <mechanism>; 
        # Supported mechanisms: LOCK-BASED, TIMESTAMP-BASED, VALIDATION-BASED, MULTI-VERSION

        try:
            # Parse the command
            # Expected format: "SET CONCURRENCY TO <mechanism>;"
            query_clean = query.strip().rstrip(';').upper()
            parts = query_clean.split()
            
            if len(parts) < 4 or parts[2] != "TO":
                return ExecutionResult(
                    transaction_id=0,
                    query=query,
                    timestamp=datetime.now(),
                    message="Error: Invalid syntax. Use: SET CONCURRENCY TO <mechanism>;"
                )
            
            # Get mechanism name 
            mechanism_parts = parts[3:]
            mechanism = "-".join(mechanism_parts).lower()
            
            # Validate mechanism
            valid_mechanisms = ["lock-based", "timestamp-based", "validation-based", "multi-version"]
            if mechanism not in valid_mechanisms:
                return ExecutionResult(
                    transaction_id=0,
                    query=query,
                    timestamp=datetime.now(),
                    message=f"Error: Unknown concurrency mechanism '{mechanism}'. "
                           f"Valid options: {', '.join(valid_mechanisms)}"
                )
            
            # Switch the mechanism
            self.cc_manager.set_concurrency_mechanism(mechanism)
            
            # Get stats to confirm
            stats = self.cc_manager.get_statistics()
            strategy_name = stats.get("strategy", "Unknown")
            
            return ExecutionResult(
                transaction_id=0,
                query=query,
                timestamp=datetime.now(),
                message=f"Concurrency control mechanism changed to: {mechanism.upper()} ({strategy_name})"
            )
            
        except Exception as e:
            return ExecutionResult(
                transaction_id=0,
                query=query,
                timestamp=datetime.now(),
                message=f"Error changing concurrency mechanism: {str(e)}"
            )
        
    def _commit(self, session: ClientSession = None) -> None:
        current_transaction_id = session.current_transaction_id if session else self.current_transaction_id

        if current_transaction_id is not None:
            self.cc_manager.commit_transaction(current_transaction_id)
            self._reset_transaction_state(session)

    def _rollback(self, session: ClientSession = None) -> None:
        current_transaction_id = session.current_transaction_id if session else self.current_transaction_id

        if current_transaction_id is not None:
            self.cc_manager.abort_transaction(
                current_transaction_id, "Error")
            self._reset_transaction_state(session)

    def _reset_transaction_state(self, session: ClientSession = None) -> None:
        if session:
            session.current_transaction_id = None
            session.multiple_transaction = False
            session.explicit_transaction = False
            session.query_storage.clear()
            session.result_storage.clear()
            session.transaction_failed = False
        else:
            self.current_transaction_id = None
            self.multiple_transaction = False
            self.explicit_transaction = False
            self.query_storage.clear()
            self.result_storage.clear()
            self.transaction_failed = False

    def _validate_ccm(self, table: str, action: str) -> None:

        response = self.cc_manager.validate_object(
            table, self.current_transaction_id, action)
        count = 0

        while not response.allowed and count < self.CCM_RETRY_MAX:
            time.sleep(self.CCM_RETRY_DELAY)
            response = self.cc_manager.validate_object(
                table, self.current_transaction_id, action)
            count += 1

        if not response.allowed:
            raise Exception(f"CCM denied {action} access on {table}")        # Actually acquire the lock after validation succeeds
        self.cc_manager.log_object(
            table, self.current_transaction_id, action)

    def _get_case_insensitive(self, row: dict, key: str, value_only: bool = False):
        """
        Get value from row dictionary with case-insensitive key matching.
        If value_only is True, returns only the value, otherwise returns (key, value) tuple.
        """
        key_lower = key.lower()
        for k, v in row.items():
            if k.lower() == key_lower:
                return v if value_only else (k, v)
        return None

    # abstraksi traverse query tree (relational algebra), recursively

    def _process_node(self, node) -> Rows:

        if node is None:
            return Rows()

        node_handlers = {
            QueryTypes.PROJECTION: self._process_projection,
            QueryTypes.RELATION: self._process_relation,
            QueryTypes.ALIAS: self._process_alias,
            QueryTypes.SELECTION_STMT: self._process_selection_stmt,
            QueryTypes.THETA_JOIN: self._process_theta_join,
            QueryTypes.NATURAL_JOIN: self._process_natural_join,
            QueryTypes.CROSS_JOIN: self._process_cross_join,
            QueryTypes.ORDER_BY: self._process_order_by,
            QueryTypes.LIMIT: self._process_limit,
            QueryTypes.CREATE_TABLE: self._create_table,
            QueryTypes.DROP_TABLE: self._drop_table,
            QueryTypes.UPDATE: self._update_rows,
            QueryTypes.INSERT: self._insert_rows,
            QueryTypes.DELETE: self._delete_rows,
        }

        handler = node_handlers.get(node.type)
        if handler:
            return handler(node)
        else:
            raise ValueError(f"Unhandled node type: {node.type}")

    def _process_projection(self, node) -> Rows:

        # π(columns)(relation): projeksi kolom tertentu
        if not node.childs:
            return Rows(data=[], rows_count=0)

        source = self._process_node(node.childs[0])
        columns = node.val if isinstance(node.val, list) else ['*']

        if not columns or columns == ['*']:
            return source

        result = []
        for row in source.data:
            proj_row = {}
            for col in columns:
                found = False
                for key, val in row.items():
                    if key.endswith('.' + col) or key == col:
                        proj_row[col] = val
                        found = True
                        break
                if not found and source.data:
                    raise ValueError(
                        f"Column '{col}' does not exist in query result")
            if proj_row:
                result.append(proj_row)

        return Rows(data=result, rows_count=len(result))

    def _process_relation(self, node) -> Rows:

        # R(table): baca seluruh isi tabel
        table_name = node.val
        self._validate_ccm(table_name, "read")

        # Log SELECT activity
        if self.current_transaction_id:
            self.cc_manager.log_operation(
                transaction_id=self.current_transaction_id,
                action="select",
                table_name=table_name
            )

        dr = DataRetrieval(table=table_name, column=[], conditions=[])
        return self.storage_manager.read_block(dr)

    def _process_alias(self, node) -> Rows:

        if not node.childs:
            return Rows()

        alias_name = node.val
        relation_node = node.childs[0]
        table_name = relation_node.val

        rows = self._process_node(relation_node)

        qualified_data = self._qualify_columns(table_name, rows.data)

        renamed_data = []
        for row in qualified_data:
            renamed_row = {}
            for key, val in row.items():
                if key.startswith(table_name + '.'):
                    new_key = alias_name + '.' + key[len(table_name) + 1:]
                    renamed_row[new_key] = val
                else:
                    renamed_row[key] = val
            renamed_data.append(renamed_row)

        return Rows(data=renamed_data, rows_count=len(renamed_data))

    def _process_selection_stmt(self, node) -> Rows:

        # σ(condition)(relation): filter baris berdasarkan kondisi
        if len(node.childs) < 2:
            return self._process_node(node.childs[0]) if node.childs else Rows()

        source = self._process_node(node.childs[0])
        condition = node.childs[1]
        return self._apply_condition(source, condition)

    def _process_order_by(self, node) -> Rows:

        if not node.childs:
            return Rows()

        source = self._process_node(node.childs[0])
        if not source.data:
            return source

        if len(node.childs) < 2 or not node.childs[1].childs:
            return source

        order_spec = node.childs[1]
        direction = order_spec.val
        col_node = order_spec.childs[0]
        col_name = col_node.val

        if col_name not in source.data[0]:
            raise ValueError(
                f"Column '{col_name}' does not exist in query result")

        reverse = str(direction).upper() == QueryTypes.DESC
        sorted_data = sorted(source.data, key=lambda x: x.get(
            col_name, 0), reverse=reverse)
        return Rows(data=sorted_data, rows_count=len(sorted_data))

    def _process_limit(self, node) -> Rows:

        if not node.childs:
            return Rows()

        source = self._process_node(node.childs[0])
        if not source.data or node.val is None:
            return source

        limit = int(node.val)
        if limit <= 0:
            return source

        return Rows(data=source.data[:limit], rows_count=len(source.data[:limit]))

    # operasi join

    def _process_theta_join(self, node) -> Rows:
        if len(node.childs) != 3:
            raise ValueError(
                f"THETA_JOIN requires exactly 3 children, got {len(node.childs)}")

        left = self._process_node(node.childs[0])
        right = self._process_node(node.childs[1])
        condition_node = node.childs[2]

        # Use table_name metadata for column qualification
        if left.table_name:
            left.data = self._qualify_columns(left.table_name, left.data)
        if right.table_name:
            right.data = self._qualify_columns(right.table_name, right.data)

        result = []
        for left_row in left.data:
            for right_row in right.data:
                merged = {**left_row, **right_row}

                if self._evaluate_condition_node(merged, condition_node):
                    result.append(merged)

        return Rows(data=result, rows_count=len(result))

    def _process_natural_join(self, node) -> Rows:
        if len(node.childs) != 2:
            raise ValueError(
                f"NATURAL_JOIN requires exactly 2 children, got {len(node.childs)}")

        left = self._process_node(node.childs[0])
        right = self._process_node(node.childs[1])
        return self._natural_join(left, right)

    def _process_cross_join(self, node) -> Rows:
        if not node.childs:
            return Rows()

        if len(node.childs) == 2:
            left = self._process_node(node.childs[0])
            right = self._process_node(node.childs[1])

            if not left.table_name:
                left.table_name = node.childs[0].val if node.childs[0].type == QueryTypes.RELATION else ""
            if not right.table_name:
                right.table_name = node.childs[1].val if node.childs[1].type == QueryTypes.RELATION else ""

            if left.table_name:
                left.data = self._qualify_columns(left.table_name, left.data)
            if right.table_name:
                right.data = self._qualify_columns(
                    right.table_name, right.data)

            result = []
            for left_row in left.data:
                for right_row in right.data:
                    merged = {**left_row, **right_row}
                    result.append(merged)

            return Rows(data=result, rows_count=len(result))
        else:
            tables = []
            for child in node.childs:
                name = child.val
                data = self._process_node(child).data
                tables.append((name, data))

            if not tables:
                return Rows()

            result = self._qualify_columns(tables[0][0], tables[0][1])
            for i in range(1, len(tables)):
                name, rows_data = tables[i]
                qual_rows = self._qualify_columns(name, rows_data)
                temp = []
                for left_row in result:
                    for right_row in qual_rows:
                        merged = {**left_row, **right_row}
                        temp.append(merged)
                result = temp

            return Rows(data=result, rows_count=len(result))

    def _natural_join(self, left: Rows, right: Rows) -> Rows:

        joined = []
        if not left.data or not right.data:
            return Rows()

        # common columns
        left_cols = set(left.data[0].keys())
        right_cols = set(right.data[0].keys())
        common_cols = left_cols & right_cols

        if not common_cols:
            return Rows(data=[], rows_count=0)

        for l_row in left.data:
            for r_row in right.data:
                match = True
                for common_col in common_cols:
                    if str(l_row.get(common_col, '')) != str(r_row.get(common_col, '')):
                        match = False
                        break

                if match:
                    new_row = l_row.copy()
                    for r_k, r_v in r_row.items():
                        if r_k not in common_cols:
                            if r_k in new_row:
                                new_row[f"{r_k}_right"] = r_v
                            else:
                                new_row[r_k] = r_v
                    joined.append(new_row)

        return Rows(data=joined, rows_count=len(joined))

    # tektokan sama SM, DML

    def _insert_rows(self, node) -> Rows:

        table = node.childs[0].val
        cols = []
        vals = []

        # Parse the structure - VALUES node should contain the values
        for child in node.childs[1:]:
            if child.type == QueryTypes.COLUMNS:
                cols = [c.val for c in child.childs]
            elif child.type == QueryTypes.VALUES:
                # Extract actual values from VALUES node
                if child.childs:
                    # Each child in VALUES is a value literal
                    vals = [c.val for c in child.childs]

        # Debug logging
        print(f"[QP] INSERT - table: {table}, cols: {cols}, vals: {vals}")

        # Validate with CC
        self._validate_ccm(table, "write")

        # Prepare the new row data for logging
        # Get schema to build complete row
        schema_file = self.storage_manager._get_schema_path(table)
        with open(schema_file, "rb") as f:
            schema = f.read()
        schema_dict = self.storage_manager.serializer.deserialize_schema(
            schema)

        # Build new_row with defaults
        new_row = {}
        for col in schema_dict["columns"]:
            new_row[col["name"]] = self.storage_manager.TYPE_DEFAULTS.get(
                col["type"], None)        # Fill in provided values
        if not cols:
            # No columns specified, use schema order
            for i, col in enumerate(schema_dict["columns"]):
                if i < len(vals):
                    new_row[col["name"]] = vals[i]
        else:
            # Columns specified
            for i, col_name in enumerate(cols):
                if i < len(vals):
                    new_row[col_name] = vals[i]

        # Validate foreign key constraints
        fk_error = self._validate_fk_on_insert(schema_dict, new_row)
        if fk_error:
            return Rows(data=[], rows_count=0, message=fk_error)

        # log operation (after validate, before storage)
        if self.current_transaction_id:
            self.cc_manager.log_operation(
                transaction_id=self.current_transaction_id,
                action="insert",
                table_name=table
            )

        # Execute the insert
        dw = DataWrite(table=table, column=cols, conditions=[], new_value=vals,
                       transaction_id=self.current_transaction_id)
        cnt = self.storage_manager.write_block(dw)
        return Rows(data=[], rows_count=cnt, message=f"{cnt} row(s) affected")

    def _update_rows(self, node) -> Rows:

        table = node.childs[0].val
        col = []
        val = []
        conditions = []

        for child in node.childs[1:]:
            if child.type == QueryTypes.SET:
                # Process all assignments, not just the first one
                for assign_node in child.childs:
                    if assign_node.type == QueryTypes.ASSIGNMENT:
                        col.append(assign_node.childs[0].val)
                        right_side = assign_node.childs[1]

                        # cek right side: expression atau literal
                        if right_side.type == QueryTypes.OPERATOR:
                            val.append(self._flatten_expression(right_side))
                        else:
                            val.append(right_side.val)
            elif child.type == QueryTypes.WHERE:
                if child.childs:
                    conditions = self._extract_conditions(child.childs[0])

        # Use table-level locking for UPDATE operations
        # (Row-level locking causes issues during strategy switching)
        self._validate_ccm(table, "write")

        # Log operation (after validate, before storage)
        if self.current_transaction_id:
            self.cc_manager.log_operation(
                transaction_id=self.current_transaction_id,
                action="update",
                table_name=table
            )

        dw = DataWrite(table=table, column=col,
                       conditions=conditions, new_value=val,
                       transaction_id=self.current_transaction_id)
        cnt = self.storage_manager.write_block(dw)
        return Rows(data=[], rows_count=cnt, message=f"{cnt} row(s) updated")

    def _delete_rows(self, node) -> Rows:

        table = node.childs[0].val
        conditions = []
        if len(node.childs) > 1:
            where_node = node.childs[1]
            if where_node.childs:
                conditions = self._extract_conditions(where_node.childs[0])

        # Use table-level locking for DELETE operations
        # (Row-level locking causes issues during strategy switching)
        self._validate_ccm(table, "write")
        
        # Log operation (after validate, before storage)
        if self.current_transaction_id:
            self.cc_manager.log_operation(
                transaction_id=self.current_transaction_id,
                action="delete",
                table_name=table
            )

        # Check and handle foreign key constraints before delete
        # First, get the rows that will be deleted
        dr = DataRetrieval(table=table, column=[], conditions=conditions)
        rows_to_delete = self.storage_manager.read_block(dr)
        
        if rows_to_delete.data:
            fk_error = self._handle_fk_on_delete(table, rows_to_delete.data)
            if fk_error:
                return Rows(data=[], rows_count=0, message=f"Error: {fk_error}")

        dd = DataDeletion(table=table, conditions=conditions,
                          transaction_id=self.current_transaction_id)
        cnt = self.storage_manager.delete_block(dd)
        return Rows(data=[], rows_count=cnt, message=f"{cnt} row(s) affected")

    def _flatten_expression(self, node) -> list:

        # konversi expression tree ke list format untuk SM
        # misal: GPA * 1.1 jadi ['GPA', '*', 1.1]

        result = []
        if node.type == QueryTypes.LITERAL:
            result.append(node.val)
        elif node.type == QueryTypes.COLUMN:
            result.append(node.val)
        elif node.type == QueryTypes.OPERATOR:
            if node.childs:
                result.extend(self._flatten_expression(node.childs[0]))
                result.append(node.val)
                if len(node.childs) > 1:
                    result.extend(self._flatten_expression(node.childs[1]))        
        return result

    # tektok sama SM, DDL (bonus)

    def _parse_create_table_sql(self, query: str) -> dict:
        """
        Parse CREATE TABLE SQL directly to support constraints.
        Format: CREATE TABLE name (
            col1 TYPE [PRIMARY KEY],
            col2 TYPE [REFERENCES other_table(col) [ON DELETE CASCADE|RESTRICT]],
            ...
            [PRIMARY KEY (col1, col2, ...)],
            [FOREIGN KEY (col) REFERENCES other_table(ref_col) [ON DELETE CASCADE|RESTRICT]]
        );
        """
        import re
        
        # Extract table name and column definitions
        match = re.match(
            r'CREATE\s+TABLE\s+(\w+)\s*\(\s*(.+)\s*\)\s*;?\s*$',
            query.strip(),
            re.IGNORECASE | re.DOTALL
        )
        
        if not match:
            return None
        
        table_name = match.group(1)
        col_defs_str = match.group(2)
        
        # Split by comma, but handle nested parentheses
        parts = self._split_column_defs(col_defs_str)
        
        columns = []
        table_constraints = []  # For table-level PRIMARY KEY and FOREIGN KEY
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            part_upper = part.upper()
            
            # Table-level PRIMARY KEY constraint
            if part_upper.startswith("PRIMARY KEY"):
                pk_match = re.match(r'PRIMARY\s+KEY\s*\(\s*(.+?)\s*\)', part, re.IGNORECASE)
                if pk_match:
                    pk_cols = [c.strip() for c in pk_match.group(1).split(',')]
                    table_constraints.append({"type": "primary_key", "columns": pk_cols})
                continue
            
            # Table-level FOREIGN KEY constraint
            if part_upper.startswith("FOREIGN KEY"):
                fk_match = re.match(
                    r'FOREIGN\s+KEY\s*\(\s*(\w+)\s*\)\s+REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)'
                    r'(?:\s+ON\s+DELETE\s+(CASCADE|RESTRICT))?',
                    part,
                    re.IGNORECASE
                )
                if fk_match:
                    table_constraints.append({
                        "type": "foreign_key",
                        "column": fk_match.group(1),
                        "ref_table": fk_match.group(2),
                        "ref_column": fk_match.group(3),
                        "on_delete": (fk_match.group(4) or "restrict").lower()
                    })
                continue
            
            # Column definition
            col_def = self._parse_column_definition(part)
            if col_def:
                columns.append(col_def)
        
        # Apply table-level constraints to columns
        for constraint in table_constraints:
            if constraint["type"] == "primary_key":
                for col_name in constraint["columns"]:
                    for col in columns:
                        if col["name"].lower() == col_name.lower():
                            col["primary_key"] = True
            elif constraint["type"] == "foreign_key":
                for col in columns:
                    if col["name"].lower() == constraint["column"].lower():
                        col["foreign_key"] = {
                            "table": constraint["ref_table"],
                            "column": constraint["ref_column"],
                            "on_delete": constraint["on_delete"]
                        }
        
        return {
            "table_name": table_name,
            "columns": columns
        }
    
    def _split_column_defs(self, col_defs_str: str) -> List[str]:
        """Split column definitions by comma, handling nested parentheses."""
        parts = []
        current = ""
        depth = 0
        
        for char in col_defs_str:
            if char == '(':
                depth += 1
                current += char
            elif char == ')':
                depth -= 1
                current += char
            elif char == ',' and depth == 0:
                parts.append(current.strip())
                current = ""
            else:
                current += char
        
        if current.strip():
            parts.append(current.strip())
        
        return parts
    
    def _parse_column_definition(self, col_def: str) -> dict:
        """Parse a single column definition."""
        import re
        
        # Pattern: col_name TYPE[(length)] [PRIMARY KEY] [REFERENCES table(col) [ON DELETE action]]
        pattern = re.compile(
            r'^(\w+)\s+'  # column name
            r'(INT|INTEGER|FLOAT|CHAR|VARCHAR)'  # type
            r'(?:\s*\(\s*(\d+)\s*\))?'  # optional length
            r'(\s+PRIMARY\s+KEY)?'  # optional inline PRIMARY KEY
            r'(?:\s+REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)'  # optional REFERENCES
            r'(?:\s+ON\s+DELETE\s+(CASCADE|RESTRICT))?)?',  # optional ON DELETE
            re.IGNORECASE
        )
        
        match = pattern.match(col_def.strip())
        if not match:
            return None
        
        col_name = match.group(1)
        col_type = match.group(2).lower()
        if col_type == "integer":
            col_type = "int"
        
        length = int(match.group(3)) if match.group(3) else None
        if length is None:
            if col_type in ["int", "float"]:
                length = 4 if col_type == "int" else 8
            else:
                length = 50  # default for char/varchar
        
        column = {
            "name": col_name,
            "type": col_type,
            "length": length
        }
        
        # Inline PRIMARY KEY
        if match.group(4):
            column["primary_key"] = True
        
        # Inline FOREIGN KEY (REFERENCES)
        if match.group(5):
            column["foreign_key"] = {
                "table": match.group(5),
                "column": match.group(6),
                "on_delete": (match.group(7) or "restrict").lower()
            }
        
        return column

    def _create_table(self, node) -> Rows:
        """
        Handle CREATE TABLE with PRIMARY KEY and FOREIGN KEY constraints.
        """
        # First, try to get raw query and parse it ourselves for constraint support
        # This is needed because Query Optimizer doesn't fully parse constraints
        
        table_name = None
        column_defs_node = None

        for child in node.childs:
            if child.type == QueryTypes.TABLE:
                table_name = child.val
            elif child.type == QueryTypes.COLUMN_DEFS:
                column_defs_node = child

        if not table_name or not column_defs_node:
            return Rows(data=[], rows_count=0, message="Invalid CREATE TABLE syntax")

        columns = []
        table_pk_columns = []  # For table-level PRIMARY KEY
        table_fk_constraints = []  # For table-level FOREIGN KEY
        
        for col_def in column_defs_node.childs:
            if col_def.type == QueryTypes.COLUMN_DEF:
                col_name = col_def.val
                col_type_str = col_def.childs[0].val if col_def.childs else "INT"

                if "(" in col_type_str:
                    type_name = col_type_str.split("(")[0].lower()
                    length = int(col_type_str.split("(")[1].rstrip(")"))
                else:
                    type_name = col_type_str.lower()
                    if type_name == "integer":
                        type_name = "int"
                    length = 4 if type_name == "int" else (8 if type_name == "float" else 50)

                column = {
                    "name": col_name,
                    "type": type_name,
                    "length": length
                }                  
                # Check for inline constraints in child nodes
                for constraint_node in col_def.childs[1:]:
                    if hasattr(constraint_node, 'type'):
                        if constraint_node.type == QueryTypes.PRIMARY_KEY_CONSTRAINT or \
                           (hasattr(constraint_node, 'val') and str(constraint_node.val).upper() == "PRIMARY KEY"):
                            column["primary_key"] = True
                        elif constraint_node.type == QueryTypes.FOREIGN_KEY_CONSTRAINT or \
                             (hasattr(constraint_node, 'val') and "REFERENCES" in str(constraint_node.val).upper()):
                            # Parse REFERENCES from inline FK constraint
                            # Structure: childs[0] = REFERENCES_TABLE, childs[1] = REFERENCES_COLUMN, childs[2] = ON DELETE action
                            if hasattr(constraint_node, 'childs') and constraint_node.childs:
                                ref_table_node = constraint_node.childs[0] if len(constraint_node.childs) > 0 else None
                                ref_col_node = constraint_node.childs[1] if len(constraint_node.childs) > 1 else None
                                on_delete_node = constraint_node.childs[2] if len(constraint_node.childs) > 2 else None
                                
                                ref_table = ref_table_node.val if ref_table_node and hasattr(ref_table_node, 'val') else ""
                                ref_col = ref_col_node.val if ref_col_node and hasattr(ref_col_node, 'val') else col_name
                                on_delete = on_delete_node.val.lower() if on_delete_node and hasattr(on_delete_node, 'val') else "restrict"
                                
                                column["foreign_key"] = {
                                    "table": ref_table,
                                    "column": ref_col,
                                    "on_delete": on_delete
                                }
                        elif hasattr(constraint_node, 'val') and str(constraint_node.val).upper() == "PRIMARY_KEY":
                            column["primary_key"] = True
                
                columns.append(column)
                # Table-level constraints
            elif col_def.type == QueryTypes.PRIMARY_KEY_CONSTRAINT:
                if col_def.childs:
                    table_pk_columns = [c.val for c in col_def.childs]
            elif col_def.type == QueryTypes.FOREIGN_KEY_CONSTRAINT:
                if col_def.childs:
                    fk_col = col_def.childs[0].val if col_def.childs else None
                    ref_table = col_def.val if hasattr(col_def, 'val') else None
                    ref_col = col_def.childs[1].val if len(col_def.childs) > 1 else fk_col
                    on_delete = "restrict"
                    if len(col_def.childs) > 2:
                        on_delete = col_def.childs[2].val.lower() if col_def.childs[2].val else "restrict"
                    table_fk_constraints.append({
                        "column": fk_col,
                        "ref_table": ref_table,
                        "ref_column": ref_col,
                        "on_delete": on_delete
                    })
        
        # Apply table-level PRIMARY KEY
        for pk_col in table_pk_columns:
            for col in columns:
                if col["name"].lower() == pk_col.lower():
                    col["primary_key"] = True
        
        # Apply table-level FOREIGN KEY
        for fk in table_fk_constraints:
            for col in columns:
                if col["name"].lower() == fk["column"].lower():
                    col["foreign_key"] = {
                        "table": fk["ref_table"],
                        "column": fk["ref_column"],
                        "on_delete": fk["on_delete"]
                    }
        
        # Validate foreign key references exist
        for col in columns:
            if col.get("foreign_key"):
                fk = col["foreign_key"]
                ref_table = fk["table"]
                ref_column = fk["column"]
                
                # Check if referenced table exists
                try:
                    ref_schema_file = self.storage_manager._get_schema_path(ref_table)
                    with open(ref_schema_file, "rb") as f:
                        ref_schema = self.storage_manager.serializer.deserialize_schema(f.read())
                    
                    # Check if referenced column exists and is primary key
                    ref_col_found = False
                    for ref_col in ref_schema["columns"]:
                        if ref_col["name"].lower() == ref_column.lower():
                            ref_col_found = True
                            if not ref_col.get("primary_key", False):
                                # Warning: referenced column is not a primary key
                                # For now, just continue (some DBs allow this)
                                pass
                            break
                    
                    if not ref_col_found:
                        return Rows(data=[], rows_count=0, 
                                    message=f"Error: Referenced column '{ref_column}' not found in table '{ref_table}'")
                except FileNotFoundError:
                    return Rows(data=[], rows_count=0, 
                                message=f"Error: Referenced table '{ref_table}' does not exist")

        schema = {
            "table_name": table_name,
            "columns": columns
        }

        try:
            self._validate_ccm(table_name, "write")
            self.storage_manager.write_table(table_name, schema)
            
            # Build success message with constraint info
            pk_cols = [c["name"] for c in columns if c.get("primary_key")]
            fk_cols = [c["name"] for c in columns if c.get("foreign_key")]
            
            msg = f"Table '{table_name}' created successfully"
            if pk_cols:
                msg += f" with PRIMARY KEY({', '.join(pk_cols)})"
            if fk_cols:
                fk_details = []
                for c in columns:
                    if c.get("foreign_key"):
                        fk = c["foreign_key"]
                        fk_details.append(f"{c['name']} -> {fk['table']}({fk['column']}) ON DELETE {fk['on_delete'].upper()}")
                msg += f", FOREIGN KEY: {', '.join(fk_details)}"
            
            return Rows(data=[], rows_count=0, message=msg)
        except FileExistsError as e:
            return Rows(data=[], rows_count=0, message=f"Error: {str(e)}")
        except Exception as e:
            return Rows(data=[], rows_count=0, message=f"Error creating table: {str(e)}")

    def _drop_table(self, node) -> Rows:

        table_name = None
        for child in node.childs:
            if child.type == QueryTypes.TABLE:
                table_name = child.val
                break        
        if not table_name:
            return Rows(data=[], rows_count=0, message="Invalid DROP TABLE syntax")

        try:
            self._validate_ccm(table_name, "write")
              # Check for dependent tables (other tables that reference this table via FK)
            dependent_tables = self._find_dependent_tables(table_name)
            
            if dependent_tables:
                # Check if any dependent table with RESTRICT has actual referencing rows
                for dep_table, dep_info in dependent_tables:
                    if dep_info["on_delete"] == "restrict":
                        # Check if there are actual rows in the dependent table referencing this table
                        try:
                            dr = DataRetrieval(table=dep_table, column=[dep_info["fk_column"]], conditions=[])
                            dep_rows = self.storage_manager.read_block(dr)
                            if dep_rows.rows_count > 0:
                                return Rows(data=[], rows_count=0, 
                                            message=f"Error: Cannot drop table '{table_name}' - {dep_rows.rows_count} row(s) in table '{dep_table}' reference this table")
                        except Exception as e:
                            print(f"[QP] Warning: Error checking dependent table {dep_table}: {e}")
                
                # Handle CASCADE: Drop dependent tables first or remove FK constraints
                # For simplicity, we'll just warn about dependent tables with CASCADE
                cascade_tables = [t for t, info in dependent_tables if info["on_delete"] == "cascade"]
                if cascade_tables:
                    # Delete all rows in dependent tables that reference this table
                    for dep_table, dep_info in dependent_tables:
                        if dep_info["on_delete"] == "cascade":
                            # Read all data from the table being dropped
                            try:
                                dr = DataRetrieval(table=table_name, column=[], conditions=[])
                                parent_rows = self.storage_manager.read_block(dr)
                                  # For each parent row, delete referencing rows in dependent table
                                for parent_row in parent_rows.data:
                                    parent_pk_value = self._get_case_insensitive(
                                        parent_row, dep_info["ref_column"], value_only=True)
                                    if parent_pk_value is not None:
                                        # Delete rows in dependent table where FK = parent PK
                                        del_conditions = [Condition(
                                            column=dep_info["fk_column"],
                                            operation="=",
                                            operand=parent_pk_value
                                        )]
                                        dd = DataDeletion(table=dep_table, conditions=del_conditions,
                                                          transaction_id=self.current_transaction_id)
                                        self.storage_manager.delete_block(dd)
                            except Exception as e:
                                print(f"[QP] Warning: Error cascading delete to {dep_table}: {e}")
            
            self.storage_manager.delete_table(table_name)
            return Rows(data=[], rows_count=0, message=f"Table '{table_name}' dropped successfully")
        except FileNotFoundError as e:
            return Rows(data=[], rows_count=0, message=f"Error: {str(e)}")
        except Exception as e:
            return Rows(data=[], rows_count=0, message=f"Error dropping table: {str(e)}")

    def _find_dependent_tables(self, table_name: str) -> List[tuple]:
        """
        Find all tables that have foreign keys referencing the given table.
        Returns list of (table_name, fk_info) tuples.
        """
        import os
        import glob
        
        dependent_tables = []
        data_dir = self.storage_manager.data_dir or self.storage_manager.DATA_FOLDER
        schema_pattern = os.path.join(data_dir, "*_schema.dat")
        
        for schema_file in glob.glob(schema_pattern):
            try:
                with open(schema_file, "rb") as f:
                    schema = self.storage_manager.serializer.deserialize_schema(f.read())
                
                # Skip the table being dropped
                if schema["table_name"].lower() == table_name.lower():
                    continue
                
                # Check each column for FK referencing our table
                for col in schema["columns"]:
                    if col.get("foreign_key"):
                        fk = col["foreign_key"]
                        if fk["table"].lower() == table_name.lower():
                            dependent_tables.append((schema["table_name"], {
                                "fk_column": col["name"],
                                "ref_column": fk["column"],
                                "on_delete": fk.get("on_delete", "restrict")
                            }))
            except Exception as e:
                print(f"[QP] Warning: Error reading schema {schema_file}: {e}")
                continue
        return dependent_tables

    def _validate_fk_on_insert(self, schema_dict: dict, new_row: dict) -> Optional[str]:
        """
        Validate foreign key constraints when inserting a new row.
        Returns error message if FK constraint is violated, None if OK.
        """
        for col in schema_dict["columns"]:
            if col.get("foreign_key"):
                fk = col["foreign_key"]
                fk_column = col["name"]
                ref_table = fk["table"]
                ref_column = fk["column"]
                
                # Get the FK value from the new row
                fk_value = new_row.get(fk_column)
                if fk_value is None:
                    # Try case-insensitive lookup
                    for k, v in new_row.items():
                        if k.lower() == fk_column.lower():
                            fk_value = v
                            break
                
                if fk_value is None:
                    continue  # No value provided, skip validation
                
                # Check if the referenced value exists in the parent table
                try:
                    conditions = [Condition(column=ref_column, operation="=", operand=fk_value)]
                    dr = DataRetrieval(table=ref_table, column=[ref_column], conditions=conditions)
                    result = self.storage_manager.read_block(dr)
                    
                    if result.rows_count == 0:
                        return f"Foreign key constraint violation: Value '{fk_value}' for column '{fk_column}' " \
                               f"does not exist in referenced table '{ref_table}' column '{ref_column}'"
                except FileNotFoundError:
                    return f"Foreign key constraint error: Referenced table '{ref_table}' does not exist"
                except Exception as e:
                    return f"Foreign key constraint error: {str(e)}"
        
        return None  # All FK constraints satisfied

    def _handle_fk_on_delete(self, table: str, rows_to_delete: List[dict]) -> Optional[str]:
        """
        Handle foreign key constraints when deleting rows from a parent table.
        - RESTRICT: Prevent delete if child rows exist
        - CASCADE: Delete child rows automatically
        Returns error message if RESTRICT blocks delete, None if OK.
        """
        if not rows_to_delete:
            return None
        
        # Get schema of the table being deleted from
        try:
            schema_file = self.storage_manager._get_schema_path(table)
            with open(schema_file, "rb") as f:
                schema = self.storage_manager.serializer.deserialize_schema(f.read())
        except FileNotFoundError:
            return None  # Table doesn't exist, nothing to check
        
        # Find primary key columns
        pk_columns = [col["name"] for col in schema["columns"] if col.get("primary_key", False)]
        if not pk_columns:
            pk_columns = [schema["columns"][0]["name"]]
        
        # Find all tables that reference this table via FK
        dependent_tables = self._find_dependent_tables(table)
        if not dependent_tables:
            return None  # No dependent tables
        
        for row in rows_to_delete:
            # Get PK value(s) from the row being deleted
            for pk_col in pk_columns:
                pk_value = self._get_case_insensitive(row, pk_col, value_only=True)
                
                if pk_value is None:
                    continue
                
                # Check each dependent table
                for dep_table, dep_info in dependent_tables:
                    fk_column = dep_info["fk_column"]
                    on_delete = dep_info.get("on_delete", "restrict")
                    
                    # Check if any child rows reference this PK value
                    try:
                        conditions = [Condition(column=fk_column, operation="=", operand=pk_value)]
                        dr = DataRetrieval(table=dep_table, column=[fk_column], conditions=conditions)
                        child_rows = self.storage_manager.read_block(dr)
                        
                        if child_rows.rows_count > 0:
                            if on_delete == "restrict":
                                return f"Foreign key constraint violation: Cannot delete from '{table}' - " \
                                       f"{child_rows.rows_count} row(s) in table '{dep_table}' reference this record"
                            elif on_delete == "cascade":
                                # Delete child rows
                                dd = DataDeletion(table=dep_table, conditions=conditions,
                                                  transaction_id=self.current_transaction_id)
                                deleted_count = self.storage_manager.delete_block(dd)
                                print(f"[QP] CASCADE DELETE: Removed {deleted_count} row(s) from '{dep_table}'")
                    except Exception as e:
                        print(f"[QP] Warning: Error checking FK constraint on {dep_table}: {e}")
                        continue
        
        return None  # All FK constraints handled

    # evaluasi kondisi

    def _validate_columns_in_condition(self, node, sample_row: dict):
        if not node or node.type != QueryTypes.OPERATOR:
            return

        if node.val in ('AND', 'OR'):
            for child in node.childs:
                self._validate_columns_in_condition(child, sample_row)
            return

        if len(node.childs) >= 2:
            left_child = node.childs[0]
            right_child = node.childs[1]

            if left_child.type == QueryTypes.COLUMN and left_child.val not in sample_row:
                raise ValueError(
                    f"Column '{left_child.val}' does not exist in query result")

            if right_child.type == QueryTypes.COLUMN and right_child.val not in sample_row:
                raise ValueError(
                    f"Column '{right_child.val}' does not exist in query result")

    def _apply_condition(self, rows: Rows, node) -> Rows:
        """Apply a condition node to filter rows"""
        
        if not rows.data or node.type != QueryTypes.OPERATOR:
            return rows

        self._validate_columns_in_condition(node, rows.data[0])

        filtered = [r for r in rows.data if self._evaluate_condition_node(r, node)]
        return Rows(data=filtered, rows_count=len(filtered))

    def _extract_conditions(self, node) -> List[Condition]:
        
        if not node or node.type != QueryTypes.OPERATOR or not node.val:
            return []

        # Logical operators (AND/OR) - recursively extract from children
        if node.val in ["AND", "OR"]:
            conditions = []
            for child in node.childs:
                conditions.extend(self._extract_conditions(child))
            return conditions

        # Comparison operators (=, <>, >, etc.)
        if len(node.childs) < 2:
            return []

        left_child = node.childs[0]
        right_child = node.childs[1]

        # Extract column name and normalize to lowercase for Storage Manager
        col = left_child.val if left_child.type == QueryTypes.COLUMN else str(left_child.val)
        
        # Handle qualified column names (table.column) - extract just the column part
        if '.' in col:
            col = col.split('.')[-1]
        
        # Normalize to lowercase for consistency with Storage Manager
        col = col.lower()
        
        op = node.val
        val = right_child.val

        try:
            val = float(val)
            if val.is_integer():
                val = int(val)
        except (ValueError, TypeError):
            pass

        return [Condition(column=col, operation=op, operand=val)]

    def _evaluate_condition_node(self, row: dict, node) -> bool:

        if not node or node.type != QueryTypes.OPERATOR:
            return True

        # handle logical operators recursively
        if node.val == "AND":
            return all(self._evaluate_condition_node(row, child) for child in node.childs)
        elif node.val == "OR":
            return any(self._evaluate_condition_node(row, child) for child in node.childs)

        # handle comparison operators
        if len(node.childs) < 2:
            return False

        left_child = node.childs[0]
        right_child = node.childs[1]
        op = node.val

        # get left value (column or literal)
        if left_child.type == QueryTypes.COLUMN:
            left_val = row.get(left_child.val)
        else:
            left_val = left_child.val

        # get right value (column or literal)
        if right_child.type == QueryTypes.COLUMN:
            right_val = row.get(right_child.val)
        else:
            right_val = right_child.val

        # use storage manager's evaluation logic for consistency
        condition = Condition(column="", operation=op, operand=right_val)
        return self.storage_manager._evaluate_condition(left_val, condition)

    # utils

    def _is_write_query(self, query: str) -> bool:

        if not query:
            return False
        first_word = query.strip().split(" ")[0].upper()
        write_types = [
            QueryTypes.UPDATE,
            QueryTypes.INSERT,
            QueryTypes.DELETE,
            QueryTypes.CREATE_TABLE,
            QueryTypes.DROP_TABLE
        ]
        return first_word in write_types

    def _qualify_columns(self, table_name: str, rows_data: List[dict]) -> List[dict]:

        # table name prefix untuk nama kolom (cross join)
        qualified = []
        for row in rows_data:
            qualified_row = {
                f"{table_name}.{col.lower()}": val for col, val in row.items()}
            qualified.append(qualified_row)
        return qualified

    def _create_error_result(self, query: str, error_msg: str) -> ExecutionResult:

        return ExecutionResult(
            transaction_id=self.current_transaction_id or 0,
            query=query,
            timestamp=datetime.now(),
            message=f"Error: {error_msg}",
            rows_count=0
        )
    