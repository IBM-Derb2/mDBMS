from datetime import datetime
import re
import time
import traceback
from dataclasses import dataclass, field
from typing import List, Any, Optional, Union
from Storage_Manager.utils import Condition, DataRetrieval, DataWrite, DataDeletion
from Storage_Manager.utils import Rows as StorageRows

@dataclass
class Rows:
    # Menampung hasil data dari eksekusi query.
    data: List[dict] = field(default_factory=list)
    rows_count: int = 0
    message: str = ""

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
    def __init__(self, optimizer, storage_manager, cc_manager, fr_manager):
        self.optimizer = optimizer
        self.storage_manager = storage_manager
        self.cc_manager = cc_manager
        self.fr_manager = fr_manager
        self.current_transaction_id = None
        self.multiple_transaction = False
        self.result_storage = []
        self.query_storage = []
        self.buffer = {}

    def execute_query(self, query: str) -> List[ExecutionResult]:
        query = query.strip()
        
        # Validasi input kosong
        if not query:
            return [ExecutionResult(
                transaction_id=self.current_transaction_id or 0,
                query="",
                timestamp=datetime.now(),
                message="Error: Empty query",
                rows_count=0
            )]
        
        query_upper = query.upper().strip()

        # Handle BEGIN TRANSACTION
        if query_upper.startswith("BEGIN"):
            return [self._handle_begin_transaction(query)]
        
        # Handle COMMIT
        if query_upper.startswith("COMMIT"):
            self.buffer.clear()
            return self._handle_commit(query)

        # Handle ROLLBACK
        if query_upper.startswith("ROLLBACK") or query_upper.startswith("ABORT"):
            return [self._handle_rollback(query)]

        # Jika mode multiple transaction aktif, simpan query
        if self.multiple_transaction:
            self.query_storage.append(query)
            return [] 

        # Single query execution
        if not query.endswith(";"):
            return [ExecutionResult(
                transaction_id=self.current_transaction_id or 0,
                query=query,
                timestamp=datetime.now(),
                message="Error: Query must end with a semicolon",
                rows_count=0
            )]

        try:
            is_implicit = False
            if self.current_transaction_id is None:
                self._handle_begin_transaction("BEGIN TRANSACTION")
                is_implicit = True
            
            parsed_query = self.optimizer.parse_query(query)
            result = self._process_node(parsed_query.query_tree)
            
            execution_result = ExecutionResult(
                data=result,
                message= result.message or "Query executed successfully",
                query=query,
                transaction_id=self.current_transaction_id,
                timestamp=datetime.now(),
                rows_count=result.rows_count if result else 0
            )
            
            if self._is_write_query(query):
                self.fr_manager.write_log(execution_result)
            
            self._commit()
            
            return [execution_result]
            
        except Exception as e:
            # print(f"[QP] Error executing query: {e}")
            traceback.print_exc()
            if self.current_transaction_id is not None:
                self._rollback()
            
            return [ExecutionResult(
                transaction_id=self.current_transaction_id or 0,
                query=query,
                timestamp=datetime.now(),
                message=f"Error: {str(e)}",
                rows_count=0
            )]

    def _is_write_query(self, query: str) -> bool:
        if not query: return False
        parts = query.strip().split(" ")
        if not parts: return False
        return parts[0].upper() in ["UPDATE", "INSERT", "DELETE", "CREATE", "DROP"]

    def _handle_begin_transaction(self, query):
        self.current_transaction_id = self.cc_manager.begin_transaction()
        self.multiple_transaction = True
        print(f"[QP] Handled BEGIN TRANSACTION. New TID: {self.current_transaction_id}")
        return ExecutionResult(
            transaction_id=self.current_transaction_id,
            query=query,
            timestamp=datetime.now(),
            message="Transaction started."
        )

    def _handle_commit(self, query):
        try:
            for q in self.query_storage:
                if not q.endswith(";"):
                    raise ValueError("Query must end with a semicolon")
                
                parsed_query = self.optimizer.parse_query(q)
                result = self._process_node(parsed_query.query_tree)
                
                execution_result = ExecutionResult(
                    data=result,
                    message="Query executed successfully",
                    query=q,
                    transaction_id=self.current_transaction_id,
                    timestamp=datetime.now(),
                    rows_count=result.rows_count if result else 0
                )
                
                if self._is_write_query(q):
                    self.fr_manager.write_log(execution_result)
                
                self.result_storage.append(execution_result)
        except Exception as e:
            self._rollback()
            return [ExecutionResult(
                transaction_id=self.current_transaction_id or 0,
                query=query,
                timestamp=datetime.now(),
                message=f"Error processing transaction: {str(e)}",
                rows_count=0
            )]
        
        self._commit()
        final_result = self.result_storage.copy()
        self.result_storage.clear()
        self.query_storage.clear()
        return final_result
    
    def _handle_rollback(self, query):
        tid = self.current_transaction_id
        if self.current_transaction_id is not None:
            self.cc_manager.abort_transaction(self.current_transaction_id, "User requested")
        
        self.current_transaction_id = None
        self.multiple_transaction = False
        
        return ExecutionResult(
            transaction_id=tid if tid else 0,
            query=query,
            timestamp=datetime.now(),
            message="Transaction rolled back."
        )
    
    def _commit(self):
        if self.current_transaction_id is not None:
            self.cc_manager.commit_transaction(self.current_transaction_id)
            self.current_transaction_id = None
            self.multiple_transaction = False

    def _rollback(self):
        if self.current_transaction_id is not None:
            self.cc_manager.abort_transaction(self.current_transaction_id, "Error")
            self.current_transaction_id = None
            self.multiple_transaction = False
    
    def _ensure_list(self, val):
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return [val]
        return []

    def _process_node(self, node) -> Rows:
        if node is None:
            return Rows()

        if node.type == "CREATE_TABLE":
            return self._create_table(node)
        elif node.type == "DROP_TABLE":
            return self._drop_table(node)
        
        elif node.type == "PROJECTION":
            columns = self._ensure_list(node.val)
            child_result = self._process_node(node.childs[0])
            return self._select_columns(child_result, columns)
            
        elif node.type == "RELATION":
            return self._from_table(node)
            
        elif node.type == "SELECTION_STMT":
            return self._process_selection_stmt(node)
            
        elif node.type == "ORDER BY":
            child_result = self._process_node(node.childs[0])
            return self._order_by(child_result, node.val)
            
        elif node.type == "LIMIT":
            child_result = self._process_node(node.childs[0])
            return self._limit(child_result, int(node.val))
            
        elif node.type == "JOIN":
            left_result = self._process_node(node.childs[0])
            right_result = self._process_node(node.childs[1])
            return self._nested_loop_join(left_result, right_result, node.val)
            
        elif node.type == "CROSS":
            return self._cartesian(node)

        elif node.type == "UPDATE":
            return self._update_table(node)
            
        elif node.type == "INSERT":
            return self._insert_table(node)
            
        elif node.type == "DELETE":
            return self._delete_table(node)
            
        else:
            return Rows(data=[], rows_count=0)
    
    def _from_table(self, node):
        table_name = node.val
        self._validate_ccm(table_name, "read")
        if table_name in self.buffer:
            print(f"[QP] Buffer Hit for table: {table_name}")
            cached_rows = self.buffer[table_name]
            return Rows(data=cached_rows.data.copy(), rows_count=cached_rows.rows_count)
        print(f"[QP] Buffer Miss. Reading from disk: {table_name}")
        data_retrieval = DataRetrieval(table=table_name, column=["*"], conditions=[])
        print(f"[QP] Sending read request for table {table_name}")
        print(f"[QP] Conditions: {data_retrieval.conditions}")
        storage_rows = self.storage_manager.read_block(data_retrieval)
        print(f"[QP] Received {len(storage_rows.data) if hasattr(storage_rows, 'data') else 0} rows, type: {type(storage_rows)}")
        qp_rows = self._convert_to_qp_rows(storage_rows)
        self.buffer[table_name] = qp_rows
        return Rows(data=qp_rows.data.copy(), rows_count=qp_rows.rows_count)

    def _convert_to_qp_rows(self, storage_rows) -> Rows:
        data_list = []
        if hasattr(storage_rows, 'data'):
            data_list = storage_rows.data
        elif isinstance(storage_rows, list):
            data_list = storage_rows
        return Rows(data=data_list, rows_count=len(data_list))
    
    def _select_columns(self, data: Rows, select_cols) -> Rows:
        if select_cols == ["*"] or select_cols == "*":
            if not isinstance(data, Rows): return self._convert_to_qp_rows(data)
            return data
        if isinstance(select_cols, str): select_cols = [select_cols]
        result_data = []
        for row in data.data:
            result_row = {}
            for col in select_cols:
                col_clean = col.split(".")[-1].lower()
                # Case insensitive search
                for k, v in row.items():
                    if k.lower() == col_clean:
                        result_row[k] = v
                        break
            result_data.append(result_row)
        return Rows(data=result_data, rows_count=len(result_data))

    def _process_selection_stmt(self, node) -> Rows:
        base_rows = self._process_node(node.childs[0])
        if len(node.childs) < 2: return base_rows
        table_name = "RESULT_SET"
        if node.childs[0].type == "RELATION":
            table_name = node.childs[0].val
        return self._condition_storage(base_rows, node.childs[1], table_name)

    def _condition_storage(self, rows: Rows, condition_node, table_name: str) -> Rows:
        """
        Menerapkan kondisi filtering
        """
        if rows.rows_count == 0:
            return rows
        conditions = self._extract_conditions(condition_node)
        dr = DataRetrieval(table=table_name, column=["*"], conditions=conditions)
        print(f"[QP] Sending conditional read request for table {table_name} with conditions: {conditions}")
        filtered_data = []
        for row in rows.data:
            if self._matches_retrieval_conditions(row, conditions):
                filtered_data.append(row)
        return Rows(data=filtered_data, rows_count=len(filtered_data))
    
    def _matches_retrieval_conditions(self, row: dict, conditions: List[Any]) -> bool:
        if not conditions: return True
        for cond in conditions:
            row_val = None
            for k, v in row.items():
                if k.lower() == cond.column.lower():
                    row_val = v
                    break
            if row_val is None: return False
            if not self._evaluate_single_condition(row_val, cond):
                return False
        return True
    
    def _evaluate_single_condition(self, val, cond: Condition) -> bool:
        op = cond.operation
        target = cond.operand
        try:
            if isinstance(val, (int, float)) and isinstance(target, (int, float, str)):
                target = float(target)
                val = float(val)
            else:
                val = str(val)
                target = str(target)
        except:
            pass

        if op == "=": return val == target
        elif op == "<>": return val != target
        elif op == ">": return val > target
        elif op == ">=": return val >= target
        elif op == "<": return val < target
        elif op == "<=": return val <= target
        return False
    
    def _extract_conditions(self, node):
        from Storage_Manager.utils import Condition
        conditions = []
        if hasattr(node, 'type'):
            if node.type == "SELECTION":
                parts = node.val.split(" ")
                if len(parts) >= 3:
                    col = parts[0].lower()
                    op = parts[1]
                    val = parts[2].strip("'")
                    try:
                        val = float(val)
                        if val.is_integer(): val = int(val)
                    except: pass
                    conditions.append(Condition(column=col, operation=op, operand=val))
            elif node.type in ["AND", "OR"]:
                for child in node.childs:
                    conditions.extend(self._extract_conditions(child))
        return conditions

    def _update_table(self, node) -> Rows:
        from Storage_Manager.utils import DataWrite
        print("\n[DEBUG UPDATE NODE]")
        print(f"Child 0 (Table): {node.childs[0].val}")
        if len(node.childs) > 1:
            print(f"Child 1 (Set/Col): {node.childs[1].val} (Type: {type(node.childs[1].val)})")
        if not node.childs: raise ValueError("Invalid UPDATE tree")
        table = node.childs[0].val
        parts = node.val.split('=')
        col = [parts[0].strip()] if len(parts) > 1 else []
        val = parts[1].strip().strip("'") if len(parts) > 1 else ""
        
        conditions = []
        if len(node.childs) > 1: conditions = self._extract_conditions(node.childs[1])
        self._validate_ccm(table, "write")
        
        dw = DataWrite(table=table, column=col, conditions=conditions, new_value=val)
        res = self.storage_manager.write_block(dw)
        if table in self.buffer: del self.buffer[table]
        cnt = self._get_affected_count(res)
        return Rows(data=[], rows_count=cnt, message=f"Updated {cnt} rows")

    def _insert_table(self, node) -> Rows:
        from Storage_Manager.utils import DataWrite
        table = node.childs[0].val
        cols = node.val.get("columns", []) if isinstance(node.val, dict) else []
        vals = node.val.get("values", []) if isinstance(node.val, dict) else []
        self._validate_ccm(table, "write")
        dw = DataWrite(table=table, column=cols, conditions=[], new_value=vals)
        res = self.storage_manager.write_block(dw)
        if table in self.buffer: del self.buffer[table]
        cnt = self._get_affected_count(res)
        return Rows(data=[], rows_count=cnt, message=f"Inserted {cnt} rows")

    def _delete_table(self, node) -> Rows:
        from Storage_Manager.utils import DataDeletion
        table = node.childs[0].val
        conditions = []
        if len(node.childs) > 1: conditions = self._extract_conditions(node.childs[1])
        self._validate_ccm(table, "write")
        dd = DataDeletion(table=table, conditions=conditions)
        res = self.storage_manager.delete_block(dd)
        if table in self.buffer: del self.buffer[table]
        return Rows(data=[], rows_count=res if isinstance(res, int) else 1, message=f"Deleted rows")

    def _order_by(self, data: Rows, order_by_val) -> Rows:
        if not data.data: return data
        
        col_name = order_by_val
        reverse = False
        
        # Check format jika optimizer mengirim list [col, direction]
        if isinstance(order_by_val, list):
            col_name = order_by_val[0]
            if len(order_by_val) > 1 and str(order_by_val[1]).upper() == "DESC":
                reverse = True
        elif isinstance(order_by_val, str) and " DESC" in order_by_val.upper():
            col_name = order_by_val.split(" ")[0]
            reverse = True

        # Lakukan sorting in-memory
        try:
            sorted_data = sorted(
                data.data, 
                key=lambda x: x.get(col_name.lower(), 0), 
                reverse=reverse
            )
            return Rows(data=sorted_data, rows_count=len(sorted_data))
        except Exception as e:
            print(f"[QP Warning] Sort failed: {e}")
            return data

    def _cartesian(self, node) -> Rows:
        if not node.childs: return Rows()
        
        # Ambil semua tabel
        tables_data = []
        for child in node.childs:
            tables_data.append(self._process_node(child).data)
            
        if not tables_data: return Rows()
        
        result = tables_data[0]
        
        # Iteratif cross join
        for i in range(1, len(tables_data)):
            next_table = tables_data[i]
            temp_res = []
            for r1 in result:
                for r2 in next_table:
                    temp_res.append({**r1, **r2}) 
            result = temp_res
            
        return Rows(data=result, rows_count=len(result))

    def _limit(self, data: Rows, limit_value: int) -> Rows:
        if not data.data: return data
        return Rows(data=data.data[:limit_value], rows_count=len(data.data[:limit_value]))

    def _nested_loop_join(self, left: Rows, right: Rows, cond) -> Rows:
        joined = []
        if not left.data or not right.data: return Rows()
        
        l_key = cond[0].split(".")[-1]
        r_key = cond[1].split(".")[-1]
        
        for l in left.data:
            for r in right.data:
                if str(l.get(l_key)) == str(r.get(r_key)):
                    joined.append({**l, **r})
        return Rows(data=joined, rows_count=len(joined))

    def _create_table(self, node) -> Rows:
        table_name = node.val
        from Storage_Manager.utils import DataWrite
        self._validate_ccm("SCHEMA", "write")

        dw = DataWrite(table="SCHEMA", column=["create"], conditions=[], new_value=f"CREATE TABLE {table_name}")
        self.storage_manager.write_block(dw)
        
        return Rows(data=[], rows_count=0, message=f"Table {table_name} created")

    def _drop_table(self, node) -> Rows:
        table_name = node.val
        self._validate_ccm(table_name, "write")
        
        from Storage_Manager.utils import DataDeletion
        dd = DataDeletion(table=table_name, conditions=[])
        self.storage_manager.delete_block(dd)
        
        return Rows(data=[], rows_count=0, message=f"Table {table_name} dropped")
    
    def _validate_ccm(self, table, action):
        response = self.cc_manager.validate_object(table, self.current_transaction_id, action)
        count = 0
        while count < 5 and not getattr(response, 'allowed', False):
            time.sleep(0.1)
            response = self.cc_manager.validate_object(table, self.current_transaction_id, action)
            count += 1
        
        if not getattr(response, 'allowed', False):
            raise Exception(f"CCM denied {action} access on {table}")

    def _get_affected_count(self, result):
        if isinstance(result, int): return result
        if hasattr(result, 'rows_count'): return result.rows_count
        return 1
