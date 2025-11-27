from datetime import datetime
import traceback
from dataclasses import dataclass, field
from typing import List, Any, Optional

from globalsy.constants.query_types import QueryTypes
from globalsy.constants.query_operators import QueryOperators
from Storage_Manager.utils import Condition, DataRetrieval, DataWrite, DataDeletion

@dataclass
class Rows:
    data: List[dict] = field(default_factory=list)
    rows_count: int = 0
    message: str = ""

@dataclass
class ExecutionResult:
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
        
        if not query:
            return [ExecutionResult(
                transaction_id=self.current_transaction_id or 0,
                query="",
                timestamp=datetime.now(),
                message="Error: Empty query",
                rows_count=0
            )]
        
        query_upper = query.upper().strip()
        
        if query_upper.startswith("BEGIN"):
            return [self._handle_begin_transaction(query)]
        
        if query_upper.startswith("COMMIT"):
            self.buffer.clear()
            return self._handle_commit(query)

        if query_upper.startswith("ROLLBACK") or query_upper.startswith("ABORT"):
            return [self._handle_rollback(query)]

        if self.multiple_transaction:
            self.query_storage.append(query)
            return [] 

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
            
            # Parsing & Optimization
            parsed_query = self.optimizer.parse_query(query)
            optimized_query = self.optimizer.optimize_query(parsed_query)
            
            # Process Tree
            result = self._process_node(optimized_query.query_tree)
            
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
        first_word = query.strip().split(" ")[0].upper()
        # Menggunakan constant jika memungkinkan, atau fallback ke string
        write_types = [
            getattr(QueryTypes, 'UPDATE', 'UPDATE'),
            getattr(QueryTypes, 'INSERT', 'INSERT'),
            getattr(QueryTypes, 'DELETE', 'DELETE'),
            getattr(QueryTypes, 'CREATE_TABLE', 'CREATE_TABLE'),
            getattr(QueryTypes, 'DROP_TABLE', 'DROP_TABLE')
        ]
        return first_word in write_types

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
        if isinstance(val, list): return val
        if isinstance(val, str): return [val]
        return []

    def _process_node(self, node) -> Rows:
        if node is None:
            return Rows()

        if node.type == QueryTypes.CREATE_TABLE:
            return self._create_table(node)
        elif node.type == QueryTypes.DROP_TABLE:
            return self._drop_table(node)
        
        elif node.type == QueryTypes.TABLE:  
            return self._from_table(node)
        
        elif node.type == QueryTypes.SELECT:
            return self._process_selection_stmt(node)
        
        elif node.type == "PROJECT" or (hasattr(QueryTypes, 'PROJECT') and node.type == QueryTypes.PROJECT):
            return self._process_projection(node)
            
        elif node.type == QueryTypes.JOIN:
            left_result = self._process_node(node.childs[0])
            right_result = self._process_node(node.childs[1])
            return self._nested_loop_join(left_result, right_result, node.val)
        elif node.type == QueryTypes.CROSS_JOIN:
            return self._cartesian(node)
            
        elif node.type == QueryTypes.UPDATE:
            return self._update_table(node)
            
        elif node.type == QueryTypes.INSERT:
            return self._insert_table(node)
            
        elif node.type == QueryTypes.DELETE:
            return self._delete_table(node)

        elif node.type == QueryTypes.FROM:
            if node.childs:
                return self._process_node(node.childs[0])
            return Rows(data=[], rows_count=0)

        else:
            print(f"[QP] Warning: Unhandled node type '{node.type}'")
            return Rows(data=[], rows_count=0)
    
    def _process_selection_stmt(self, node) -> Rows:
        """
        Process SELECT node (SQL Structure).
        Expects children: COLUMNS, FROM, WHERE, ORDER_BY, LIMIT
        """
        columns_node = None
        from_node = None
        where_node = None
        limit_node = None
        order_by_node = None

        for child in node.childs:
            if child.type == QueryTypes.COLUMNS:
                columns_node = child
            elif child.type == QueryTypes.FROM:
                from_node = child
            elif child.type == QueryTypes.WHERE:
                where_node = child
            elif child.type == QueryTypes.LIMIT:
                limit_node = child
            elif child.type == QueryTypes.ORDER_BY:
                order_by_node = child

        if not from_node:
            return Rows(data=[], rows_count=0)

        base_rows = self._process_from_clause(from_node)

        if where_node and where_node.childs:
            conditions = self._extract_conditions(where_node.childs[0])
            filtered_data = []
            for row in base_rows.data:
                if self._matches_retrieval_conditions(row, conditions):
                    filtered_data.append(row)
            base_rows = Rows(data=filtered_data, rows_count=len(filtered_data))

        if order_by_node:
            base_rows = self._apply_order_by(base_rows, order_by_node)

        if limit_node:
            base_rows = self._limit(base_rows, int(limit_node.val))

        if columns_node:
            base_rows = self._apply_column_selection(base_rows, columns_node)

        return base_rows
    
    def _process_from_clause(self, from_node) -> Rows:
        if not from_node.childs:
            return Rows(data=[], rows_count=0)
        
        join_node = None
        left_table_node = None
        
        for child in from_node.childs:
            if child.type == QueryTypes.JOIN:
                join_node = child
            elif child.type == QueryTypes.TABLE or child.type == "PROJECT":
                if left_table_node is None:
                    left_table_node = child
        
        if join_node:
            left_data = self._process_node(left_table_node)
            
            if len(join_node.childs) >= 1:
                right_table_node = join_node.childs[0]
                right_data = self._process_node(right_table_node)
                
                if join_node.val == 'NATURAL':
                    return self._natural_join(left_data, right_data)
                
                operator_node = None
                for child in join_node.childs:
                    if child.type == "OPERATOR":
                        operator_node = child
                        break
                
                if operator_node and len(operator_node.childs) >= 2:
                    left_col = operator_node.childs[0].val
                    right_col = operator_node.childs[1].val
                    return self._nested_loop_join(left_data, right_data, [left_col, right_col])
            
            return Rows(data=[], rows_count=0)
        else:
            return self._process_node(left_table_node) if left_table_node else Rows(data=[], rows_count=0)

    def _process_projection(self, node) -> Rows:
        if not node.childs:
            return Rows(data=[], rows_count=0)
        
        base_data = self._process_node(node.childs[0])
        
        return base_data

    def _apply_column_selection(self, data: Rows, columns_node) -> Rows:
        if not columns_node.childs:
            if columns_node.val == "*": 
                return data
            return data

        columns = [col.val for col in columns_node.childs]
        if "*" in columns:
            return data
            
        return self._select_columns(data, columns)
    
    def _condition_storage(self, rows: Rows, condition_node, table_name: str) -> Rows:
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
    

    def _from_table(self, node):
        table_name = node.val
        self._validate_ccm(table_name, "read")
        
        if table_name in self.buffer:
            print(f"[QP] Buffer Hit for table: {table_name}")
            cached_rows = self.buffer[table_name]
            return Rows(data=cached_rows.data.copy(), rows_count=cached_rows.rows_count)
            
        print(f"[QP] Buffer Miss. Reading from disk: {table_name}")
        data_retrieval = DataRetrieval(table=table_name, column=["*"], conditions=[])
        storage_rows = self.storage_manager.read_block(data_retrieval)
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
                for k, v in row.items():
                    if k.lower() == col_clean:
                        result_row[k] = v
                        break
            result_data.append(result_row)
        return Rows(data=result_data, rows_count=len(result_data))

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

        if op == QueryOperators.EQ: return val == target
        elif op == QueryOperators.ALT_NEQ or op == QueryOperators.NEQ: return val != target
        elif op == QueryOperators.GT: return val > target
        elif op == QueryOperators.GTE: return val >= target
        elif op == QueryOperators.LT: return val < target
        elif op == QueryOperators.LTE: return val <= target
        return False
    
    def _extract_conditions(self, node):
        conditions = []
        if hasattr(node, 'type'):
            if node.type == "OPERATOR" or (hasattr(QueryTypes, 'OPERATOR') and node.type == QueryTypes.OPERATOR):
                if node.val and len(node.childs) >= 2:
                    left_child = node.childs[0]
                    right_child = node.childs[1]
                    
                    if hasattr(left_child, 'type') and left_child.type == 'COLUMN':
                        col = left_child.val
                    else:
                        col = str(left_child.val) if hasattr(left_child, 'val') else str(left_child)
                    
                    if '.' in col:
                        col = col.split('.')[-1]
                    col = col.lower()
                    
                    op = node.val
                    
                    if hasattr(right_child, 'type') and right_child.type == 'LITERAL':
                        val = right_child.val
                    else:
                        val = right_child.val if hasattr(right_child, 'val') else right_child
                    
                    try:
                        val = float(val)
                        if val.is_integer(): val = int(val)
                    except: pass
                    conditions.append(Condition(column=col, operation=op, operand=val))
            elif node.type == getattr(QueryTypes, 'CONDITION', 'CONDITION') or node.type == QueryTypes.WHERE:
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
            
            if node.childs:
                for child in node.childs:
                    conditions.extend(self._extract_conditions(child))
        return conditions

    def _update_table(self, node) -> Rows:
        table = node.childs[0].val
        parts = node.val.split('=')
        col = [parts[0].strip()] if len(parts) > 1 else []
        val = parts[1].strip().strip("'") if len(parts) > 1 else ""
        
        conditions = []
        if len(node.childs) > 1:
             conditions = self._extract_conditions(node.childs[1])
        
        self._validate_ccm(table, "write")
        
        dw = DataWrite(table=table, column=col, conditions=conditions, new_value=val)
        res = self.storage_manager.write_block(dw)
        if table in self.buffer: del self.buffer[table]
        cnt = self._get_affected_count(res)
        return Rows(data=[], rows_count=cnt, message=f"Updated {cnt} rows")

    def _insert_table(self, node) -> Rows:
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
        table = node.childs[0].val
        conditions = []
        if len(node.childs) > 1: conditions = self._extract_conditions(node.childs[1])
        self._validate_ccm(table, "write")
        dd = DataDeletion(table=table, conditions=conditions)
        res = self.storage_manager.delete_block(dd)
        if table in self.buffer: del self.buffer[table]
        return Rows(data=[], rows_count=res if isinstance(res, int) else 1, message=f"Deleted rows")

    def _apply_order_by(self, data: Rows, order_by_node) -> Rows:
        if not order_by_node.childs: return data
        order_item = order_by_node.childs[0]
        direction = order_item.val
        if order_item.childs:
            col_node = order_item.childs[0]
            col_name = col_node.val
            return self._order_by(data, [col_name, direction])
        return data

    def _order_by(self, data: Rows, order_by_val) -> Rows:
        if not data.data: return data
        col_name = order_by_val
        reverse = False
        if isinstance(order_by_val, list):
            col_name = order_by_val[0]
            if len(order_by_val) > 1 and str(order_by_val[1]).upper() == QueryTypes.DESC:
                reverse = True
        elif isinstance(order_by_val, str) and f" {QueryTypes.DESC}" in order_by_val.upper():
            col_name = order_by_val.split(" ")[0]
            reverse = True

        try:
            actual_col = None
            if data.data:
                for key in data.data[0].keys():
                    if key.lower() == col_name.lower():
                        actual_col = key
                        break
            if actual_col is None: return data
            sorted_data = sorted(data.data, key=lambda x: x.get(actual_col, 0), reverse=reverse)
            return Rows(data=sorted_data, rows_count=len(sorted_data))
        except Exception:
            return data

    def _natural_join(self, left: Rows, right: Rows) -> Rows:
        joined = []
        if not left.data or not right.data:
            return Rows()
        
        left_cols = {k.lower(): k for k in left.data[0].keys()}
        right_cols = {k.lower(): k for k in right.data[0].keys()}
        common_cols_lower = set(left_cols.keys()) & set(right_cols.keys())
        
        if not common_cols_lower:
            return Rows(data=[], rows_count=0)
        
        for l_row in left.data:
            for r_row in right.data:
                match = True
                for common_col_lower in common_cols_lower:
                    l_key = left_cols[common_col_lower]
                    r_key = right_cols[common_col_lower]
                    
                    if str(l_row.get(l_key, '')) != str(r_row.get(r_key, '')):
                        match = False
                        break
                
                if match:
                    new_row = l_row.copy()
                    for r_k, r_v in r_row.items():
                        if r_k.lower() not in common_cols_lower:
                            if r_k in new_row:
                                new_row[f"{r_k}_right"] = r_v
                            else:
                                new_row[r_k] = r_v
                    joined.append(new_row)
        
        return Rows(data=joined, rows_count=len(joined))

    def _nested_loop_join(self, left: Rows, right: Rows, cond) -> Rows:
        joined = []
        if not left.data or not right.data: return Rows()
        
        l_key_raw = cond[0].split(".")[-1]
        r_key_raw = cond[1].split(".")[-1]
        
        def get_val(row, key):
            for k, v in row.items():
                if k.lower() == key.lower(): return v, k
            return None, None

        for l in left.data:
            for r in right.data:
                l_val, l_real_key = get_val(l, l_key_raw)
                r_val, r_real_key = get_val(r, r_key_raw)
                
                if str(l_val) == str(r_val):
                    new_row = l.copy()
                    for r_k, r_v in r.items():
                        if r_k.lower() == r_key_raw.lower():
                            continue
                        if r_k in new_row:
                            new_row[f"{r_k}_right"] = r_v
                        else:
                            new_row[r_k] = r_v
                    joined.append(new_row)
                    
        return Rows(data=joined, rows_count=len(joined))

    def _create_table(self, node) -> Rows:
        table_name = node.val
        dw = DataWrite(table="SCHEMA", column=["create"], conditions=[], new_value=f"CREATE TABLE {table_name}")
        self.storage_manager.write_block(dw)
        return Rows(data=[], rows_count=0, message=f"Table {table_name} created")

    def _drop_table(self, node) -> Rows:
        table_name = node.val
        self._validate_ccm(table_name, "write")
        dd = DataDeletion(table=table_name, conditions=[])
        self.storage_manager.delete_block(dd)
        return Rows(data=[], rows_count=0, message=f"Table {table_name} dropped")
    
    def _validate_ccm(self, table, action):
        import time
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

    def _limit(self, data: Rows, limit_value: int) -> Rows:
        
        if not data.data: return data
        return Rows(data=data.data[:limit_value], rows_count=len(data.data[:limit_value]))
    
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
                    new_row = r1.copy()
                    for r2_k, r2_v in r2.items():
                        if r2_k in new_row:
                            new_row[f"{r2_k}_right"] = r2_v
                        else:
                            new_row[r2_k] = r2_v
                    temp_res.append(new_row)
            result = temp_res
            
        return Rows(data=result, rows_count=len(result))