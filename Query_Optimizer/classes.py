from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class QueryTree:
    type: str = "root"
    val: str = "SELECT"
    childs: List['QueryTree'] = field(default_factory=list)
    parent: Optional['QueryTree'] = None

@dataclass
class ParsedQuery:
    query_str: str
    query_tree: QueryTree = field(default_factory=QueryTree)
    plan_details: str = "" 

class OptimizationEngine:
    def parse_query(self, query: str) -> ParsedQuery:
        print(f"[Optimizer Mock] Parsing query: '{query}'")
        return ParsedQuery(query_str=query)

    def optimize_query(self, query: ParsedQuery) -> ParsedQuery:
        print(f"[Optimizer Mock] Optimizing query: '{query.query_str}'")
        query.plan_details = "Optimized Plan (e.g., Use Index Scan on 'ID')"
        return query

    def get_cost(self, query: ParsedQuery) -> int:
        print("[Optimizer Mock] Calculating cost...")
        return 10 # Biaya dummy