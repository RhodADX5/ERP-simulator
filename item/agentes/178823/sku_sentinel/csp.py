"""Motor genérico de Satisfacción de Restricciones (CSP).

Implementa consistencia de nodo (restricciones unarias) y el algoritmo AC-3
(consistencia de arco para restricciones binarias), tal como se vio en el
Parcial 1. Además de reducir dominios, registra *qué restricción* dejó vacío
cada dominio, para que el agente pueda explicar por qué rechaza un artículo.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable


@dataclass
class Conflict:
    variable: str
    constraint: str
    detail: str


@dataclass
class CSPResult:
    consistent: bool
    domains: dict[str, set]
    conflicts: list[Conflict]
    revisions: int                       # número de revisiones de arco realizadas (evidencia de AC-3)
    pruned: dict[str, list] = field(default_factory=dict)   # valores eliminados por variable


class CSP:
    def __init__(self) -> None:
        self.domains: dict[str, set] = {}
        self.unary: list[tuple[str, Callable[[Any], bool], str, Callable[[Any], str] | None]] = []
        self.binary: list[tuple[str, str, Callable[[Any, Any], bool], str]] = []

    # -- definición -------------------------------------------------------
    def add_variable(self, name: str, domain: set[Hashable]) -> None:
        self.domains[name] = set(domain)

    def add_unary(self, var: str, predicate: Callable[[Any], bool], name: str,
                  explain: Callable[[Any], str] | None = None) -> None:
        """Restricción sobre una sola variable. `explain(valor)` describe por qué falla."""
        self.unary.append((var, predicate, name, explain))

    def add_binary(self, x: str, y: str, predicate: Callable[[Any, Any], bool], name: str) -> None:
        """Restricción binaria predicate(valor_x, valor_y)."""
        self.binary.append((x, y, predicate, name))

    # -- resolución -------------------------------------------------------
    def solve(self) -> CSPResult:
        domains = {v: set(d) for v, d in self.domains.items()}
        conflicts: list[Conflict] = []
        pruned: dict[str, list] = {v: [] for v in domains}

        # 1) Consistencia de nodo
        for var, predicate, name, explain in self.unary:
            before = set(domains[var])
            kept = {val for val in before if predicate(val)}
            removed = before - kept
            pruned[var].extend(sorted(map(str, removed)))
            domains[var] = kept
            if before and not kept:
                detail = "; ".join(explain(v) for v in sorted(before, key=str)) if explain else \
                    f"ningún valor de {sorted(map(str, before))} cumple"
                conflicts.append(Conflict(var, name, detail))

        # 2) AC-3
        arcs: dict[tuple[str, str], list[tuple[Callable[[Any, Any], bool], str]]] = {}
        for x, y, predicate, name in self.binary:
            arcs.setdefault((x, y), []).append((predicate, name))
            arcs.setdefault((y, x), []).append((lambda b, a, p=predicate: p(a, b), name))

        queue = deque(arcs.keys())
        revisions = 0
        while queue:
            xi, xj = queue.popleft()
            if not domains[xi] or not domains[xj]:
                continue
            revisions += 1
            changed, failing = self._revise(domains, xi, xj, arcs[(xi, xj)])
            if changed:
                pruned[xi].extend(changed)
                if not domains[xi]:
                    conflicts.append(Conflict(
                        xi, failing,
                        f"ningún valor de {xi} {sorted(changed)} es compatible con {xj} {sorted(map(str, domains[xj]))}"))
                    continue
                for (xk, xl) in arcs:
                    if xl == xi and xk != xj:
                        queue.append((xk, xi))

        consistent = all(domains.values()) and not conflicts
        return CSPResult(consistent, domains, conflicts, revisions, {k: v for k, v in pruned.items() if v})

    @staticmethod
    def _revise(domains, xi, xj, constraints) -> tuple[list, str]:
        removed: list = []
        failing = constraints[0][1]
        for vx in list(domains[xi]):
            ok = True
            for predicate, name in constraints:
                if not any(predicate(vx, vy) for vy in domains[xj]):
                    ok = False
                    failing = name
                    break
            if not ok:
                domains[xi].discard(vx)
                removed.append(str(vx))
        return removed, failing
