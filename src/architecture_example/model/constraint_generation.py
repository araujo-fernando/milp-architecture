"""Funções puras para gerar os coeficientes de restrições em paralelo."""

from collections.abc import Iterable

_WORKER_X: dict[tuple[int, int, int], int] = {}


def initialize_subtour_worker(x: dict[tuple[int, int, int], int]) -> None:
    """Instala o mapa de índices em um subinterpretador de trabalho."""
    global _WORKER_X
    _WORKER_X = x


def generate_subtour_indices(
    subsets: Iterable[tuple[int, tuple[int, ...]]], vehicles: tuple[int, ...]
) -> list[tuple[list[int], float]]:
    """Gera apenas índices e RHS; objetos CPLEX permanecem no processo principal."""
    x = _WORKER_X
    return [
        ([x[i, j, k] for i in subset for j in subset if (i, j, k) in x], float(size - 1))
        for size, subset in subsets
        for k in vehicles
    ]
