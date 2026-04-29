"""
ddl_lineage.graph
=================
Graph algorithms operating on the lineage graph:
  - Cycle detection (DFS-based)
  - Impact analysis (BFS upstream / downstream)
  - Topological sort
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from .models import LineageEdge


# ---------------------------------------------------------------------------
# Adjacency helpers
# ---------------------------------------------------------------------------

def _build_adj(edges: list[LineageEdge]) -> tuple[dict, dict]:
    """
    Build forward and backward adjacency maps.

    Returns (fwd, bwd) where:
      fwd[source] = set of targets  (source reads/writes/FK target)
      bwd[target] = set of sources  (who depends on target)
    """
    fwd: dict[str, set[str]] = defaultdict(set)
    bwd: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        fwd[e.source].add(e.target)
        bwd[e.target].add(e.source)
    return fwd, bwd


def _bfs(start: str, graph: dict[str, set[str]]) -> set[str]:
    """Return all nodes reachable from *start* in *graph* (BFS)."""
    visited: set[str] = set()
    q: deque[str] = deque([start])
    while q:
        node = q.popleft()
        for nb in graph.get(node, set()):
            if nb not in visited:
                visited.add(nb)
                q.append(nb)
    return visited


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

def detect_cycles(node_names: list[str], edges: list[LineageEdge]) -> list[list[str]]:
    """
    Find all simple cycles using iterative DFS.

    Returns a list of cycles; each cycle is a list of node names
    where the first and last element are the same.

    Example:
        [["a", "b", "c", "a"], ["x", "y", "x"]]
    """
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.source].append(e.target)

    visited: set[str] = set()
    path: list[str] = []
    in_path: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        visited.add(node)
        path.append(node)
        in_path.add(node)

        for nb in adj[node]:
            if nb not in visited:
                dfs(nb)
            elif nb in in_path:
                start_idx = path.index(nb)
                cycle = path[start_idx:] + [nb]
                # Deduplicate: rotate to canonical form
                min_node = min(cycle[:-1])
                idx = cycle.index(min_node)
                canonical = cycle[idx:-1] + cycle[:idx] + [cycle[idx]]
                if canonical not in cycles:
                    cycles.append(canonical)

        path.pop()
        in_path.discard(node)

    for n in node_names:
        if n not in visited:
            dfs(n)

    return cycles


# ---------------------------------------------------------------------------
# Impact analysis
# ---------------------------------------------------------------------------

@dataclass
class ImpactResult:
    """Result of an impact analysis for a single target object."""

    target: str
    upstream: list[str] = field(default_factory=list)
    downstream: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Impact analysis: {self.target}",
            "=" * 44,
            f"  Upstream   (depends on): {', '.join(self.upstream) or 'none'}",
            f"  Downstream (used by):    {', '.join(self.downstream) or 'none'}",
        ]
        return "\n".join(lines)


def impact_analysis(
    target: str,
    edges: list[LineageEdge],
    edge_types: set[str] | None = None,
) -> ImpactResult:
    """
    Compute upstream and downstream reachability for *target*.

    :param target:      The object name to analyse (case-insensitive match applied).
    :param edges:       All lineage edges in the graph.
    :param edge_types:  Restrict traversal to these edge types.
                        None = use all types.

    Upstream   = objects that *target* transitively reads from.
    Downstream = objects that transitively depend on / read from *target*.
    """
    target = target.lower()
    filtered = edges if edge_types is None else [e for e in edges if e.edge_type in edge_types]
    fwd, bwd = _build_adj(filtered)

    upstream = _bfs(target, fwd) - {target}
    downstream = _bfs(target, bwd) - {target}

    return ImpactResult(
        target=target,
        upstream=sorted(upstream),
        downstream=sorted(downstream),
    )


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------

def topological_sort(node_names: list[str], edges: list[LineageEdge]) -> list[str]:
    """
    Return nodes in topological order (dependencies first).

    If the graph has cycles the affected nodes are appended at the end
    in alphabetical order with a ``*`` prefix.
    """
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {n: 0 for n in node_names}

    for e in edges:
        if e.source in in_degree and e.target in in_degree:
            adj[e.source].append(e.target)
            in_degree[e.target] += 1

    q: deque[str] = deque(n for n in node_names if in_degree[n] == 0)
    result: list[str] = []

    while q:
        node = q.popleft()
        result.append(node)
        for nb in sorted(adj[node]):
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                q.append(nb)

    # Nodes not added = part of a cycle
    remaining = sorted(n for n in node_names if in_degree.get(n, 0) > 0)
    result.extend(f"*{n}" for n in remaining)

    return result
