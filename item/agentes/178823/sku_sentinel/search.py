"""Búsqueda de sustitutos en el grafo de compatibilidad (Parcial 2).

* BFS: encuentra el sustituto con stock más cercano en número de saltos.
* Greedy Best-First Search: expande primero el nodo con menor h(n), donde
  h(n) = distancia de atributos técnicos ponderada + penalización por precio.
  Prioriza el reemplazo más parecido al original, aunque esté más lejos.

Ambas funciones reciben `neighbors(sku) -> list[str]` para no depender de
dónde vive el grafo (Neo4j o la tabla Item_Compatibility).
"""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass
from typing import Callable

PRICE_WEIGHT = 0.25


@dataclass
class SearchResult:
    algorithm: str
    found: str | None
    path: list[str]
    explored: list[str]

    @property
    def hops(self) -> int | None:
        return len(self.path) - 1 if self.found else None


def _path(parents: dict[str, str | None], node: str) -> list[str]:
    out = [node]
    while parents[out[-1]] is not None:
        out.append(parents[out[-1]])
    return out[::-1]


def bfs(origin: str, neighbors: Callable[[str], list[str]], is_goal: Callable[[str], bool]) -> SearchResult:
    parents: dict[str, str | None] = {origin: None}
    frontier = deque([origin])
    explored: list[str] = []
    while frontier:
        node = frontier.popleft()
        explored.append(node)
        for nxt in sorted(neighbors(node)):
            if nxt in parents:
                continue
            parents[nxt] = node
            if is_goal(nxt):                      # prueba de meta al generar (BFS)
                return SearchResult("BFS", nxt, _path(parents, nxt), explored)
            frontier.append(nxt)
    return SearchResult("BFS", None, [], explored)


def greedy_best_first(origin: str, neighbors: Callable[[str], list[str]], is_goal: Callable[[str], bool],
                      h: Callable[[str], float]) -> SearchResult:
    parents: dict[str, str | None] = {origin: None}
    frontier: list[tuple[float, str]] = [(h(origin), origin)]
    explored: list[str] = []
    seen = {origin}
    while frontier:
        _, node = heapq.heappop(frontier)
        explored.append(node)
        if node != origin and is_goal(node):      # prueba de meta al expandir (Greedy)
            return SearchResult("Greedy Best-First", node, _path(parents, node), explored)
        for nxt in sorted(neighbors(node)):
            if nxt in seen:
                continue
            seen.add(nxt)
            parents[nxt] = node
            heapq.heappush(frontier, (h(nxt), nxt))
    return SearchResult("Greedy Best-First", None, [], explored)


def similarity_heuristic(origin: dict, candidate: dict, key_attrs: list[str], required: list[str]) -> float:
    """h(n) en [0, ~1.25]: 0 = idéntico. Los atributos funcionales pesan el doble."""
    if candidate["SKU"] == origin["SKU"]:
        return 0.0
    total = diff = 0.0
    oa, ca = origin.get("attrs", {}), candidate.get("attrs", {})
    for attr in key_attrs:
        weight = 2.0 if attr in required else 1.0
        total += weight
        if str(oa.get(attr, "")).casefold() != str(ca.get(attr, "")).casefold():
            diff += weight
    attr_distance = diff / total if total else 1.0
    base = float(origin.get("ListPrice") or 0) or 1.0
    price_penalty = abs(float(candidate.get("ListPrice") or 0) - base) / base
    return round(attr_distance + PRICE_WEIGHT * price_penalty, 4)
