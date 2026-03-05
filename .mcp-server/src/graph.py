"""
Graph: Wiki-link graph engine with backlink index and MOC hub detection.

Builds a bidirectional graph from wiki-link outlinks, identifies MOC hubs,
and supports BFS traversal to N hops with configurable direction.
"""

from collections import deque
from dataclasses import dataclass, field

from atlas import NoteMetadata


@dataclass
class GraphNode:
    name: str
    outlinks: list[str] = field(default_factory=list)
    backlinks: list[str] = field(default_factory=list)
    is_moc: bool = False


@dataclass
class GraphResult:
    center: str
    outlinks: list[str]
    backlinks: list[str]
    mocs: list[str]          # MOC hubs connected to this note
    graph: dict[str, dict]   # Subgraph at requested depth


class GraphEngine:
    """Wiki-link graph with backlink index and MOC hub detection."""

    def __init__(self, notes: list[NoteMetadata]):
        self._nodes: dict[str, GraphNode] = {}
        self._moc_names: set[str] = set()

        # Build forward links from atlas data
        all_names = {n.name for n in notes}

        for note in notes:
            node = GraphNode(
                name=note.name,
                outlinks=[link for link in note.outlinks if link in all_names],
                is_moc=note.is_moc,
            )
            self._nodes[note.name] = node
            if note.is_moc:
                self._moc_names.add(note.name)

        # Build backlinks (reverse index)
        for name, node in self._nodes.items():
            for target in node.outlinks:
                if target in self._nodes:
                    self._nodes[target].backlinks.append(name)

    def get_node(self, name: str) -> GraphNode | None:
        """Get a single node by name."""
        return self._nodes.get(name)

    def get_connections(
        self,
        name: str,
        depth: int = 1,
        direction: str = "both",
    ) -> GraphResult | None:
        """
        Get connections for a note via BFS traversal.

        Args:
            name: Note name to start from
            depth: How many hops to follow (1-3)
            direction: "outlinks", "backlinks", or "both"

        Returns:
            GraphResult with direct connections and subgraph at depth
        """
        if name not in self._nodes:
            return None

        depth = max(1, min(depth, 3))  # Clamp to 1-3
        center_node = self._nodes[name]

        # BFS traversal
        visited: set[str] = {name}
        queue: deque[tuple[str, int]] = deque([(name, 0)])
        subgraph: dict[str, dict] = {}

        while queue:
            current_name, current_depth = queue.popleft()
            current_node = self._nodes.get(current_name)
            if current_node is None:
                continue

            # Determine neighbors based on direction
            neighbors = []
            out = current_node.outlinks if direction in ("outlinks", "both") else []
            back = current_node.backlinks if direction in ("backlinks", "both") else []
            neighbors = list(set(out + back))

            subgraph[current_name] = {
                "outlinks": current_node.outlinks,
                "backlinks": current_node.backlinks,
                "is_moc": current_node.is_moc,
            }

            if current_depth < depth:
                for neighbor in neighbors:
                    if neighbor not in visited and neighbor in self._nodes:
                        visited.add(neighbor)
                        queue.append((neighbor, current_depth + 1))

        # Find connected MOCs
        connected_mocs = [
            n for n in visited
            if n in self._moc_names and n != name
        ]

        return GraphResult(
            center=name,
            outlinks=center_node.outlinks,
            backlinks=center_node.backlinks,
            mocs=connected_mocs,
            graph=subgraph,
        )

    def find_path(self, start: str, end: str, max_depth: int = 6) -> list[str] | None:
        """
        Find shortest path between two notes through the link graph.
        Returns list of note names forming the path, or None if no path found.
        """
        if start not in self._nodes or end not in self._nodes:
            return None
        if start == end:
            return [start]

        # BFS for shortest path
        visited = {start}
        queue: deque[tuple[str, list[str]]] = deque([(start, [start])])

        while queue:
            current, path = queue.popleft()
            if len(path) > max_depth:
                continue

            node = self._nodes.get(current)
            if node is None:
                continue

            # Check both directions for path finding
            neighbors = set(node.outlinks + node.backlinks)
            for neighbor in neighbors:
                if neighbor == end:
                    return path + [end]
                if neighbor not in visited and neighbor in self._nodes:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None  # No path found within depth

    def get_mocs(self) -> list[dict]:
        """List all MOC hub notes with their connection counts."""
        mocs = []
        for name in sorted(self._moc_names):
            node = self._nodes[name]
            mocs.append({
                "name": name,
                "outlinks_count": len(node.outlinks),
                "backlinks_count": len(node.backlinks),
                "total_connections": len(set(node.outlinks + node.backlinks)),
            })
        return sorted(mocs, key=lambda m: -m["total_connections"])

    def stats(self) -> dict:
        """Graph-level statistics."""
        total_links = sum(len(n.outlinks) for n in self._nodes.values())
        linked_notes = sum(1 for n in self._nodes.values() if n.outlinks or n.backlinks)
        orphaned = sum(1 for n in self._nodes.values() if not n.outlinks and not n.backlinks)
        max_outlinks = max((len(n.outlinks) for n in self._nodes.values()), default=0)
        max_backlinks = max((len(n.backlinks) for n in self._nodes.values()), default=0)

        return {
            "total_notes": len(self._nodes),
            "total_links": total_links,
            "linked_notes": linked_notes,
            "orphaned_notes": orphaned,
            "moc_count": len(self._moc_names),
            "avg_outlinks": round(total_links / max(len(self._nodes), 1), 1),
            "max_outlinks": max_outlinks,
            "max_backlinks": max_backlinks,
        }


# ── CLI test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

    from atlas import get_atlas

    notes = get_atlas()
    graph = GraphEngine(notes)

    # Print graph stats
    s = graph.stats()
    print("=== Graph Stats ===")
    for k, v in s.items():
        print(f"  {k}: {v}")

    # Show MOC hubs
    print("\n=== MOC Hubs (top 10) ===")
    for moc in graph.get_mocs()[:10]:
        print(f"  {moc['name']}: {moc['total_connections']} connections "
              f"({moc['outlinks_count']} out, {moc['backlinks_count']} back)")

    # Test traversal if name provided
    if len(sys.argv) > 1:
        name = " ".join(sys.argv[1:])
        result = graph.get_connections(name, depth=1)
        if result:
            print(f"\n=== Connections for '{name}' ===")
            print(f"  Outlinks ({len(result.outlinks)}): {result.outlinks[:5]}...")
            print(f"  Backlinks ({len(result.backlinks)}): {result.backlinks[:5]}...")
            print(f"  Connected MOCs: {result.mocs}")
        else:
            print(f"\nNote '{name}' not found in graph")
