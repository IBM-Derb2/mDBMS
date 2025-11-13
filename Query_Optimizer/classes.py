from dataclasses import dataclass, field
from typing import List, Optional
from .optimization_engine import OptimizationEngine


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


__all__ = ['OptimizationEngine', 'QueryTree', 'ParsedQuery']
