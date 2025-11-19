"""
Database Statistics Module

Integrates with Storage Manager to get real table statistics for cost-based query optimization.
Falls back to mock statistics if storage manager is not available.
"""

from typing import Dict, Optional

# Try to import Storage Manager
try:
    from Storage_Manager.storage_engine import StorageEngine
    from Storage_Manager.utils import Statistic
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False


class TableStatistics:
    """Statistics for a single table"""

    def __init__(self, name: str, row_count: int, avg_row_size: int = 100):
        self.name = name
        self.row_count = row_count
        self.avg_row_size = avg_row_size
        self.column_stats = {}

    def add_column_stats(self, column: str, distinct_values: int, null_count: int = 0,
                         min_value=None, max_value=None, avg_value=None):
        """Add statistics for a specific column"""
        self.column_stats[column] = {
            'distinct_values': distinct_values,
            'null_count': null_count,
            'selectivity': distinct_values / self.row_count if self.row_count > 0 else 1.0,
            'min': min_value,
            'max': max_value,
            'avg': avg_value
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

    def __init__(self, use_storage_manager=True):
        self.tables: Dict[str, TableStatistics] = {}
        self.storage_engine = None

        # Try to use real storage manager first
        if use_storage_manager and STORAGE_AVAILABLE:
            try:
                self.storage_engine = StorageEngine()
                self._load_stats_from_storage()
            except Exception as e:
                print(f"Warning: Could not load storage manager: {e}")
                self._initialize_default_stats()
        else:
            self._initialize_default_stats()

    def _load_stats_from_storage(self):
        """Load statistics from Storage Manager for existing tables"""
        if not self.storage_engine:
            return

        # Try to load stats for common tables
        table_names = ['users', 'orders', 'products', 'categories']

        for table_name in table_names:
            try:
                storage_stats = self.storage_engine.get_stats(table_name)

                # Convert Storage Manager statistics to our format
                table_stats = TableStatistics(
                    name=table_name,
                    row_count=storage_stats.n_r,
                    avg_row_size=storage_stats.l_r
                )

                # Add column statistics from V_a_r
                for col_name, distinct_count in storage_stats.V_a_r.items():
                    table_stats.add_column_stats(
                        column=col_name,
                        distinct_values=distinct_count,
                        null_count=0  # Storage Manager doesn't track nulls yet
                    )

                self.tables[table_name] = table_stats
                print(
                    f"✓ Loaded stats for '{table_name}': {storage_stats.n_r:,} rows")

            except Exception as e:
                # Table doesn't exist or error loading stats
                pass

        # If no tables loaded, use default stats
        if not self.tables:
            print("No tables found in storage, using default mock statistics")
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

    def estimate_selectivity(self, table_name: str, column: str, operator: str) -> float:
        """
        Estimate selectivity of a condition

        Selectivity = fraction of rows that satisfy the condition (0.0 to 1.0)
        """
        stats = self.get_table_stats(table_name)
        if not stats or column not in stats.column_stats:
            # Default selectivity estimates
            if operator in ['=', '!=']:
                return 0.1  # 10% for equality
            elif operator in ['<', '<=', '>', '>=']:
                return 0.3  # 30% for range
            else:
                return 0.5  # 50% for unknown

        col_stats = stats.column_stats[column]

        # Selectivity based on operator and column stats
        if operator == '=':
            # For equality, selectivity = 1 / distinct_values
            return 1.0 / col_stats['distinct_values']
        elif operator == '!=':
            return 1.0 - (1.0 / col_stats['distinct_values'])
        elif operator in ['<', '<=', '>', '>=']:
            # For range queries, estimate 33% selectivity
            return 0.33
        else:
            return col_stats['selectivity']

    def print_all_statistics(self):
        """Print all database statistics"""
        print("="*80)
        print("DATABASE STATISTICS")
        print("="*80)
        print(f"\nTotal Tables: {len(self.tables)}")
        print(
            f"Total Rows: {sum(t.row_count for t in self.tables.values()):,}")
        print()

        for table_name in sorted(self.tables.keys()):
            table = self.tables[table_name]
            print(table)
            print()

        print("="*80)


# Global statistics manager instance
_stats_manager = None


def get_statistics_manager() -> StatisticsManager:
    """Get the global statistics manager instance"""
    global _stats_manager
    if _stats_manager is None:
        _stats_manager = StatisticsManager()
    return _stats_manager


def print_statistics():
    """Convenience function to print all statistics"""
    mgr = get_statistics_manager()
    mgr.print_all_statistics()
