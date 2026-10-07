"""Reconstrução limitada das rotas usando os arcos binários selecionados."""

from collections import defaultdict

from cvrp.domain.instance import InstanceData
from cvrp.domain.results import ModelSolution, Route
from cvrp.validation.solution import SolutionError


def extract_routes(data: InstanceData, solution: ModelSolution) -> tuple[Route, ...]:
    arcs_by_vehicle: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for i, j, k in solution.arcs:
        if (i, j, k) not in data.cost:
            raise SolutionError(f"Arco escolhido fora da instância: {(i, j, k)}")
        arcs_by_vehicle[k].append((i, j))
    return tuple(_route(data, k, arcs) for k, arcs in sorted(arcs_by_vehicle.items()))


def _route(data: InstanceData, vehicle: int, arcs: list[tuple[int, int]]) -> Route:
    successors = dict(arcs)
    if len(successors) != len(arcs) or len({j for _, j in arcs}) != len(arcs):
        raise SolutionError("Mais de uma entrada/saída no nó")
    sequence, consumed, node = [], set(), 0
    for _ in range(len(data.customers) + 1):
        if node not in successors:
            raise SolutionError("Rota sem retorno ao depósito")
        destination = successors[node]
        if (node, destination) in consumed:
            raise SolutionError("Ciclo inválido na rota")
        consumed.add((node, destination))
        node = destination
        if node == 0:
            break
        sequence.append(data.nodes[node])
    if node != 0 or consumed != set(arcs):
        raise SolutionError("Arcos desconectados ou ciclo inválido")
    return Route(data.vehicles[vehicle].identifier, tuple(sequence))
