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

    def __init__(self, optimizer, storage_manager, cc_manager, fr_manager):
        self.optimizer = optimizer
        self.storage_manager = storage_manager
        self.cc_manager = cc_manager
        self.fr_manager = fr_manager

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

        if query_upper.startswith("BEGIN"):
            return [self._handle_begin_transaction(query, client_address)]

        if query_upper.startswith("COMMIT"):
            return self._handle_commit(query, client_address)

        if query_upper.startswith("ROLLBACK") or query_upper.startswith("ABORT"):
            return [self._handle_rollback(query, client_address)]

        if query_upper.startswith("SET CONCURRENCY"):
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
            raise Exception(f"CCM denied {action} access on {table}")

        # Actually acquire the lock after validation succeeds
        self.cc_manager.log_object(
            table, self.current_transaction_id, action)

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
                col["type"], None)

        # Fill in provided values
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
        val = None
        conditions = []

        for child in node.childs[1:]:
            if child.type == QueryTypes.SET:
                if child.childs and child.childs[0].type == QueryTypes.ASSIGNMENT:
                    assign = child.childs[0]
                    col = [assign.childs[0].val]
                    right_side = assign.childs[1]

                    # cek right side: expression atau literal
                    if right_side.type == QueryTypes.OPERATOR:
                        val = self._flatten_expression(right_side)
                    else:
                        val = right_side.val
            elif child.type == QueryTypes.WHERE:
                if child.childs:
                    conditions = self._extract_conditions(child.childs[0])

        # First, acquire read lock to identify affected rows
        if conditions:
            # Acquire read lock on table to read data
            self._validate_ccm(table, "read")

            # Read current data to identify rows that match conditions
            dr = DataRetrieval(table=table, column=[], conditions=conditions)
            affected_rows = self.storage_manager.read_block(dr)

            # Acquire exclusive locks on each affected row
            if affected_rows.data:
                # Get primary key column(s)
                schema_file = self.storage_manager._get_schema_path(table)
                with open(schema_file, "rb") as f:
                    schema = f.read()
                schema_dict = self.storage_manager.serializer.deserialize_schema(
                    schema)
                pk_columns = [col["name"] for col in schema_dict["columns"]
                              if col.get("primary_key", False)]
                if not pk_columns:
                    pk_columns = [schema_dict["columns"][0]["name"]]

                # Lock each affected row
                for row in affected_rows.data:
                    pk_values = ":".join(str(row.get(pk_col))
                                         for pk_col in pk_columns)
                    row_id = f"{table}:row:{pk_values}"
                    self._validate_ccm(row_id, "write")
        else:
            # No WHERE clause - validate table-level lock (affects all rows)
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

        # First, acquire read lock to identify affected rows
        if conditions:
            # Acquire read lock on table to read data
            self._validate_ccm(table, "read")

            # Read current data to identify rows that match conditions
            dr = DataRetrieval(table=table, column=[], conditions=conditions)
            affected_rows = self.storage_manager.read_block(dr)

            # Acquire exclusive locks on each affected row
            if affected_rows.data:
                # Get primary key column(s)
                schema_file = self.storage_manager._get_schema_path(table)
                with open(schema_file, "rb") as f:
                    schema = f.read()
                schema_dict = self.storage_manager.serializer.deserialize_schema(
                    schema)
                pk_columns = [col["name"] for col in schema_dict["columns"]
                              if col.get("primary_key", False)]
                if not pk_columns:
                    pk_columns = [schema_dict["columns"][0]["name"]]

                # Lock each affected row
                for row in affected_rows.data:
                    pk_values = ":".join(str(row.get(pk_col))
                                         for pk_col in pk_columns)
                    row_id = f"{table}:row:{pk_values}"
                    self._validate_ccm(row_id, "write")
        else:
            # No WHERE clause - validate table-level lock (affects all rows)
            self._validate_ccm(table, "write")

        # Log operation (after validate, before storage)
        if self.current_transaction_id:
            self.cc_manager.log_operation(
                transaction_id=self.current_transaction_id,
                action="delete",
                table_name=table
            )

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

    def _create_table(self, node) -> Rows:

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
        for col_def in column_defs_node.childs:
            if col_def.type == QueryTypes.COLUMN_DEF:
                col_name = col_def.val
                col_type = col_def.childs[0].val if col_def.childs else "INT"

                if "(" in col_type:
                    type_name = col_type.split("(")[0].lower()
                    length = int(col_type.split("(")[1].rstrip(")"))
                else:
                    type_name = col_type.lower()
                    length = 4 if type_name in ["int", "float"] else 50

                columns.append({
                    "name": col_name,
                    "type": type_name,
                    "length": length
                })

        schema = {
            "table_name": table_name,
            "columns": columns
        }

        try:
            self._validate_ccm(table_name, "write")
            self.storage_manager.write_table(table_name, schema)
            return Rows(data=[], rows_count=0, message=f"Table '{table_name}' created successfully")
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
            self.storage_manager.delete_table(table_name)
            return Rows(data=[], rows_count=0, message=f"Table '{table_name}' dropped successfully")
        except FileNotFoundError as e:
            return Rows(data=[], rows_count=0, message=f"Error: {str(e)}")
        except Exception as e:
            return Rows(data=[], rows_count=0, message=f"Error dropping table: {str(e)}")

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

        col = left_child.val if left_child.type == QueryTypes.COLUMN else str(left_child.val)
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
    