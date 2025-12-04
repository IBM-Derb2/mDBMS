"""
Database Statistics Module

Integrates with Storage Manager to get real table statistics for cost-based query optimization.
Falls back to mock statistics if storage manager is not available.
"""

import logging
from typing import Dict, Optional
from globalsy.constants.query_operators import QueryOperators

logger = logging.getLogger(__name__)



class TableStatistics:
    """Statistics for a single table"""

    def __init__(self, name: str, row_count: int, avg_row_size: int = 100):
        self.name = name
        self.row_count = row_count
        self.avg_row_size = avg_row_size
        self.column_stats = {}

    def add_column_stats(self, column: str, distinct_values: int, null_count: int = 0,
                         min_value=None, max_value=None, avg_value=None, histogram=None):
        """Add statistics for a specific column"""
        self.column_stats[column] = {
            'distinct_values': distinct_values,
            'null_count': null_count,
            'selectivity': distinct_values / self.row_count if self.row_count > 0 else 1.0,
            'min': min_value,
            'max': max_value,
            'avg': avg_value,
            'histogram': histogram  # For refined selectivity estimates
        }

    def __str__(self):
        """String representation of table statistics"""
        lines = [f"Table: {self.name}"]
        lines.append(f"  Rows: {self.row_count:,}")
        lines.append(f"  Avg Row Size: {self.avg_row_size} bytes")
        lines.append(f"  Columns:")
        for col, stats in self.column_stats.items():
            line = f"    {col}: distinct={stats['distinct_values']:,}, nulls={stats['null_count']}"
            if stats.get('min') is not None:
                line += f", min={stats['min']}, max={stats['max']}"
            if stats.get('avg') is not None:
                line += f", avg={stats['avg']:.1f}"
            lines.append(line)
        return "\n".join(lines)


class StatisticsManager:
    """Manages database statistics for cost estimation"""

    def __init__(self, storage_engine=None):
        self.tables: Dict[str, TableStatistics] = {}
        self.storage_engine = storage_engine

        if self.storage_engine:
            self._load_stats_from_storage()
        else:
            self._initialize_default_stats()

    def _load_stats_from_storage(self):
        """Load statistics from Storage Manager for existing tables"""
        if not self.storage_engine:
            return

        table_names = ['users', 'orders', 'products', 'categories', 'student', 'attends', 'course']

        for table_name in table_names:
            storage_stats = self.storage_engine.get_stats(table_name)
            if not storage_stats:
                continue

            table_stats = TableStatistics(
                name=table_name,
                row_count=storage_stats.n_r,
                avg_row_size=storage_stats.l_r
            )

            for col_name, distinct_count in storage_stats.V_a_r.items():
                table_stats.add_column_stats(
                    column=col_name,
                    distinct_values=distinct_count,
                    null_count=0
                )

            self.tables[table_name] = table_stats
            logger.debug(f"Loaded stats for '{table_name}': {storage_stats.n_r:,} rows")

        if not self.tables:
            logger.debug("No tables found in storage, using default mock statistics")
            self._initialize_default_stats()

    def _initialize_default_stats(self):
        """Initialize with default test statistics"""

        # Users table - large table (10,000 rows)
        users = TableStatistics('users', row_count=10000, avg_row_size=120)
        users.add_column_stats('id', distinct_values=10000, null_count=0,
                               min_value=1, max_value=10000, avg_value=5000.5)
        users.add_column_stats('name', distinct_values=9500, null_count=0,
                               min_value='Aaron', max_value='Zoe')
        users.add_column_stats('age', distinct_values=80, null_count=100,
                               min_value=18, max_value=95, avg_value=42.5)
        users.add_column_stats('city', distinct_values=100, null_count=50,
                               min_value='Atlanta', max_value='Washington')
        users.add_column_stats('salary', distinct_values=5000, null_count=200,
                               min_value=20000, max_value=200000, avg_value=65000)
        self.tables['users'] = users

        # Orders table - very large table (100,000 rows)
        orders = TableStatistics('orders', row_count=100000, avg_row_size=80)
        orders.add_column_stats('id', distinct_values=100000, null_count=0,
                                min_value=1, max_value=100000, avg_value=50000.5)
        orders.add_column_stats('user_id', distinct_values=10000, null_count=0,
                                min_value=1, max_value=10000, avg_value=5000)
        orders.add_column_stats('product_id', distinct_values=1000, null_count=0,
                                min_value=1, max_value=1000, avg_value=500)
        orders.add_column_stats('total', distinct_values=50000, null_count=0,
                                min_value=10, max_value=10000, avg_value=250)
        orders.add_column_stats('status', distinct_values=5, null_count=0,
                                min_value='cancelled', max_value='shipped')
        self.tables['orders'] = orders

        # Products table - medium table (1,000 rows)
        products = TableStatistics(
            'products', row_count=1000, avg_row_size=150)
        products.add_column_stats('id', distinct_values=1000, null_count=0,
                                  min_value=1, max_value=1000, avg_value=500.5)
        products.add_column_stats('name', distinct_values=950, null_count=0,
                                  min_value='Apple', max_value='Zoom Lens')
        products.add_column_stats('price', distinct_values=500, null_count=0,
                                  min_value=10, max_value=5000, avg_value=250)
        products.add_column_stats('category_id', distinct_values=50, null_count=0,
                                  min_value=1, max_value=50, avg_value=25)
        products.add_column_stats('stock', distinct_values=100, null_count=0,
                                  min_value=0, max_value=1000, avg_value=150)
        self.tables['products'] = products

        # Categories table - small table (50 rows)
        categories = TableStatistics(
            'categories', row_count=50, avg_row_size=60)
        categories.add_column_stats('id', distinct_values=50, null_count=0,
                                    min_value=1, max_value=50, avg_value=25.5)
        categories.add_column_stats('name', distinct_values=50, null_count=0,
                                    min_value='Books', max_value='Toys')
        self.tables['categories'] = categories

    def get_table_stats(self, table_name: str) -> Optional[TableStatistics]:
        """Get statistics for a table"""
        # Handle table aliases by removing alias part
        base_name = table_name.split()[0].lower()
        return self.tables.get(base_name)

    def get_row_count(self, table_name: str) -> int:
        """Get row count for a table"""
        stats = self.get_table_stats(table_name)
        return stats.row_count if stats else 1000  # Default if not found

    def estimate_selectivity(self, table_name: str, column: str, operator: str, value=None) -> float:
        """
        Estimate selectivity of a condition using database theory formulas

        Selectivity = fraction of rows that satisfy the condition (0.0 to 1.0)

        Formulas from Database System Concepts:
        - σ_A=v(r): n_r / V(A,r) where V(A,r) is number of distinct values
        - σ_A≤v(r): 0 if v < min(A,r), else (v - min(A,r)) / (max(A,r) - min(A,r))
        - Conjunction (AND): multiply selectivities
        - Disjunction (OR): 1 - (1-s1)*(1-s2)*...*(1-sn)
        - Negation (NOT): 1 - selectivity
        """
        stats = self.get_table_stats(table_name)
        if not stats or column not in stats.column_stats:
            # Default selectivity estimates
            if operator in [QueryOperators.EQ, QueryOperators.NEQ]:
                return 0.1  # 10% for equality
            elif operator in [QueryOperators.LT, QueryOperators.LTE, QueryOperators.GT, QueryOperators.GTE]:
                return 0.3  # 30% for range
            else:
                return 0.5  # 50% for unknown

        col_stats = stats.column_stats[column]
        n_r = stats.row_count
        V_A_r = col_stats['distinct_values']

        # Selectivity based on operator and column stats
        if operator == QueryOperators.EQ:
            # σ_A=v(r): Equality condition on a key attribute = 1
            # For non-key: selectivity = n_r / V(A,r) = 1 / V(A,r) (normalized)
            if V_A_r == n_r:  # Unique column (key)
                return 1.0 / n_r
            else:
                return 1.0 / V_A_r

        elif operator == QueryOperators.NEQ:
            # Negation: 1 - selectivity of equality
            eq_selectivity = 1.0 / V_A_r
            return 1.0 - eq_selectivity

        elif operator in [QueryOperators.LT, QueryOperators.LTE, QueryOperators.GT, QueryOperators.GTE]:
            # σ_A≤v(r): Range condition
            # If min/max available, use formula: (v - min(A,r)) / (max(A,r) - min(A,r))
            if col_stats['min'] is not None and col_stats['max'] is not None and value is not None:
                min_val = col_stats['min']
                max_val = col_stats['max']

                try:
                    # Convert to numeric for comparison
                    min_val = float(min_val) if not isinstance(
                        min_val, (int, float)) else min_val
                    max_val = float(max_val) if not isinstance(
                        max_val, (int, float)) else max_val
                    val = float(value) if not isinstance(
                        value, (int, float)) else value

                    if max_val == min_val:
                        return 0.5  # All values are the same

                    if operator in [QueryOperators.LT, QueryOperators.LTE]:
                        if val < min_val:
                            return 0.0
                        elif val > max_val:
                            return 1.0
                        else:
                            selectivity = (val - min_val) / (max_val - min_val)
                            return min(1.0, max(0.0, selectivity))
                    else:  # '>' or '>='
                        if val > max_val:
                            return 0.0
                        elif val < min_val:
                            return 1.0
                        else:
                            selectivity = (max_val - val) / (max_val - min_val)
                            return min(1.0, max(0.0, selectivity))
                except (ValueError, TypeError):
                    # Fall back to default if conversion fails
                    pass

            # Default for range queries without min/max info
            return 0.33
        else:
            return col_stats['selectivity']

    def estimate_conjunction_selectivity(self, selectivities: list) -> float:
        """
        Estimate selectivity for conjunction (AND) of conditions
        Formula: s1 * s2 * ... * sn (assuming independence)
        """
        result = 1.0
        for s in selectivities:
            result *= s
        return result

    def estimate_disjunction_selectivity(self, selectivities: list) -> float:
        """
        Estimate selectivity for disjunction (OR) of conditions
        Formula: 1 - (1-s1) * (1-s2) * ... * (1-sn)
        """
        result = 1.0
        for s in selectivities:
            result *= (1.0 - s)
        return 1.0 - result

    def estimate_negation_selectivity(self, selectivity: float) -> float:
        """
        Estimate selectivity for negation (NOT) of condition
        Formula: 1 - selectivity
        """
        return 1.0 - selectivity

    def calculate_cost(self, node, estimated_rows: int = None) -> tuple[int, int]:
        from globalsy.classes.query_tree import QueryTree
        from globalsy.constants.query_types import QueryTypes

        if node.type == QueryTypes.PROJECTION:
            return self._calculate_projection_cost(node, estimated_rows)
        elif node.type == QueryTypes.SELECTION_STMT:
            return self._calculate_selection_cost(node)
        elif node.type == QueryTypes.THETA_JOIN:
            return self._calculate_join_cost(node)
        elif node.type == QueryTypes.CROSS_JOIN:
            return self._calculate_cross_join_cost(node)
        elif node.type == QueryTypes.NATURAL_JOIN:
            return self._calculate_natural_join_cost(node)
        elif node.type == QueryTypes.RELATION:
            return self._calculate_relation_cost(node)
        elif node.type == QueryTypes.ALIAS:
            if node.childs:
                return self.calculate_cost(node.childs[0], estimated_rows)
            return 0, 0
        elif node.type == QueryTypes.ORDER_BY:
            if node.childs:
                cost, rows = self.calculate_cost(node.childs[0], estimated_rows)
                return cost + (rows * 10), rows
            return 0, 0
        elif node.type == QueryTypes.LIMIT:
            if node.childs:
                cost, rows = self.calculate_cost(node.childs[0], estimated_rows)
                limit = int(node.val) if node.val else rows
                return cost, min(rows, limit)
            return 0, 0
        else:
            total_cost = 0
            total_rows = estimated_rows if estimated_rows else 1000
            for child in node.childs:
                child_cost, child_rows = self.calculate_cost(child, estimated_rows)
                total_cost += child_cost
                if child_rows:
                    total_rows = child_rows
            return total_cost, total_rows

    def _calculate_projection_cost(self, node, estimated_rows):
        if not node.childs:
            return 0, 0
        cost, rows = self.calculate_cost(node.childs[0], estimated_rows)
        return cost + (rows * 2), rows

    def _calculate_selection_cost(self, node):
        if len(node.childs) < 2:
            if node.childs:
                return self.calculate_cost(node.childs[0])
            return 0, 0

        source_cost, source_rows = self.calculate_cost(node.childs[0])
        condition = node.childs[1]

        from globalsy.constants.query_types import QueryTypes
        selectivity = 0.5
        if condition.type == QueryTypes.OPERATOR:
            selectivity = self._estimate_selectivity_from_condition(condition)

        result_rows = int(source_rows * selectivity)
        filter_cost = source_rows * 3
        return source_cost + filter_cost, result_rows

    def _calculate_relation_cost(self, node):
        table_name = node.val
        row_count = self.get_row_count(table_name)
        return row_count * 5, row_count

    def _calculate_join_cost(self, node):
        if len(node.childs) < 2:
            return 0, 0

        left_cost, left_rows = self.calculate_cost(node.childs[0])
        right_cost, right_rows = self.calculate_cost(node.childs[1])

        result_rows = max(left_rows, right_rows)
        if len(node.childs) >= 3:
            result_rows = int(result_rows * 0.8)

        smaller_rows = min(left_rows, right_rows)
        larger_rows = max(left_rows, right_rows)
        join_cost = smaller_rows * 5 + larger_rows * 3 + result_rows * 2

        return left_cost + right_cost + join_cost, result_rows

    def _calculate_cross_join_cost(self, node):
        if len(node.childs) < 2:
            return 0, 0

        left_cost, left_rows = self.calculate_cost(node.childs[0])
        right_cost, right_rows = self.calculate_cost(node.childs[1])

        result_rows = left_rows * right_rows
        join_cost = result_rows * 10

        return left_cost + right_cost + join_cost, result_rows

    def _calculate_natural_join_cost(self, node):
        return self._calculate_join_cost(node)

    def _estimate_selectivity_from_condition(self, condition):
        from globalsy.constants.query_operators import QueryOperators

        if condition.val == QueryOperators.AND:
            selectivities = [self._estimate_selectivity_from_condition(child) for child in condition.childs]
            return self.estimate_conjunction_selectivity(selectivities)
        elif condition.val == QueryOperators.OR:
            selectivities = [self._estimate_selectivity_from_condition(child) for child in condition.childs]
            return self.estimate_disjunction_selectivity(selectivities)
        elif condition.val in [QueryOperators.EQ, QueryOperators.NEQ, QueryOperators.LT, QueryOperators.LTE, QueryOperators.GT, QueryOperators.GTE]:
            if condition.val == QueryOperators.EQ:
                return 0.1
            elif condition.val in [QueryOperators.LT, QueryOperators.GT, QueryOperators.LTE, QueryOperators.GTE]:
                return 0.33
            elif condition.val == QueryOperators.NEQ:
                return 0.9
        return 0.5

    def print_all_statistics(self):
        logger.info("="*80)
        logger.info("DATABASE STATISTICS")
        logger.info("="*80)
        logger.info(f"\nTotal Tables: {len(self.tables)}")
        logger.info(f"Total Rows: {sum(t.row_count for t in self.tables.values()):,}")
        logger.info("")

        for table_name in sorted(self.tables.keys()):
            table = self.tables[table_name]
            logger.info(str(table))
            logger.info("")

        logger.info("="*80)
