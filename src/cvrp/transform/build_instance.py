"""Dados operacionais tipados → problema canônico → instância de cada split."""

from collections import defaultdict

from cvrp.config import DistanceMode
from cvrp.domain.instance import Customer, InstanceData, Location, ProblemData, ProblemSplit, TravelData, Vehicle
from cvrp.domain.raw import Place, RawScenario
from cvrp.domain.results import Diagnostic
from cvrp.io.reader import InputError, ScenarioReader, valid_date
from cvrp.validation.input import InputValidator
from cvrp.validation.instance import InstanceValidator, ProblemValidator


class InstanceTransformer:
    def __init__(
        self,
        raw: object,
        cd: str,
        delivery_date: str | None = None,
        *,
        distance_mode: DistanceMode = "complete_with_geography",
    ) -> None:
        self.raw = raw if isinstance(raw, RawScenario) else ScenarioReader().decode(raw)
        self.cd = cd
        self.delivery_date = valid_date(self.raw.reference_date if delivery_date is None else delivery_date)
        self.distance_mode = distance_mode

    def prepare(self) -> ProblemData:
        """Converte unidades e agrega sem materializar pares de clientes."""
        InputValidator().validate(self.raw)
        depot = next((p for p in self.raw.depots if p.code == self.cd), None)
        if depot is None:
            raise InputError(f"Código não encontrado: {self.cd}")
        if not depot.active:
            raise InputError(f"CD inativo: {self.cd}")
        location = _location(depot)
        customers, diagnostics = self._customers()
        travel = TravelData(
            locations={self.cd: location, **{c.identifier: c.location for c in customers.values()}},
            overrides={(d.origin, d.destination): d.distance_km for d in self.raw.distances},
            blocked=self._blocked(),
            mode=self.distance_mode,
        )
        problem = ProblemData(
            location,
            self.delivery_date,
            customers,
            self._vehicles(),
            travel,
            self.raw.fixed_vehicle_cost,
            self.raw.currency,
            tuple(diagnostics),
        )
        ProblemValidator().validate(problem)
        return problem

    def transform(self) -> InstanceData:
        """Compatibilidade: materializa um único problema sem clusterização."""
        problem = self.prepare()
        return materialize(problem, ProblemSplit("split-001", tuple(problem.customers), problem.vehicles))

    def _customers(self) -> tuple[dict[str, Customer], list[Diagnostic]]:
        clients = {c.code: c for c in self.raw.clients}
        products = {p.sku: p for p in self.raw.products}
        loads: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        references: dict[str, list[str]] = defaultdict(list)
        diagnostics: list[Diagnostic] = []
        seen: set[str] = set()
        for order in self.raw.orders:
            if order.number in seen:
                diagnostics.append(Diagnostic("pedido_duplicado", "Pedido idêntico deduplicado", order.number))
                continue
            seen.add(order.number)
            if order.status != "CONFIRMADO" or order.delivery_date != self.delivery_date:
                diagnostics.append(
                    Diagnostic("pedido_filtrado", "Status/data não elegíveis", order.number, level="INFO")
                )
                continue
            client = clients.get(order.customer_code)
            if not self._eligible(client, order.number, order.customer_code, diagnostics):
                continue
            code = order.customer_code
            loads[code][0] += sum(item.boxes * products[item.sku].weight_kg for item in order.items)
            loads[code][1] += sum(item.boxes * products[item.sku].volume_m3 for item in order.items)
            references[code].append(order.number)
        customers = {
            code: Customer(_location(clients[code]), load[0], load[1], tuple(references[code]))
            for code, load in sorted(loads.items())
        }
        return customers, diagnostics

    def _eligible(self, client: Place | None, order: str, client_code: str, diagnostics: list[Diagnostic]) -> bool:
        if client is None:
            diagnostics.append(Diagnostic("cliente_nao_cadastrado", f"Pedido {order} descartado", client_code))
            return False
        if client.depot_code != self.cd:
            diagnostics.append(Diagnostic("outro_cd", f"Pedido {order} pertence a outro CD", client.code, level="INFO"))
            return False
        if client.latitude is None or client.longitude is None:
            diagnostics.append(Diagnostic("coordenada_ausente", f"Pedido {order} descartado", client.code))
            return False
        return True

    def _vehicles(self) -> tuple[Vehicle, ...]:
        kinds = {kind.code: kind for kind in self.raw.vehicle_kinds}
        counts: dict[str, int] = defaultdict(int)
        for available in self.raw.availability:
            if available.depot_code == self.cd:
                counts[available.kind] += available.quantity - available.maintenance
        return tuple(
            Vehicle(
                f"{code}-{self.cd}-{number + 1:02d}",
                code,
                kinds[code].capacity_kg,
                kinds[code].capacity_m3,
                self.raw.cost_per_km * kinds[code].relative_cost,
            )
            for code, count in sorted(counts.items())
            for number in range(count)
        )

    def _blocked(self) -> dict[str, frozenset[str]]:
        blocked: dict[str, set[str]] = defaultdict(set)
        for rule in self.raw.circulation:
            if rule.depot_code == self.cd:
                blocked[rule.vehicle_kind].update(rule.customer_codes)
        return {kind: frozenset(clients) for kind, clients in blocked.items()}


def _location(place: Place) -> Location:
    if place.latitude is None or place.longitude is None:
        raise InputError(f"Coordenada obrigatória: {place.code}")
    return Location(place.code, place.name, place.latitude, place.longitude)


def materialize(problem: ProblemData, split: ProblemSplit) -> InstanceData:
    """Calcula custos/adjacências somente para os clientes do split."""
    nodes = (problem.depot.identifier, *split.customer_ids)
    distances: dict[tuple[int, int], float] = {}
    costs: dict[tuple[int, int, int], float] = {}
    outgoing: dict[tuple[int, int], list[int]] = defaultdict(list)
    incoming: dict[tuple[int, int], list[int]] = defaultdict(list)
    for k, vehicle in enumerate(split.vehicles):
        for i, origin in enumerate(nodes):
            for j, destination in enumerate(nodes):
                if problem.travel.allows(origin, destination, vehicle):
                    if (i, j) not in distances:
                        distances[i, j] = problem.travel.distance(origin, destination)
                    costs[i, j, k] = distances[i, j] * vehicle.cost_per_km
                    outgoing[i, k].append(j)
                    incoming[j, k].append(i)
    data = InstanceData(
        depot=problem.depot.identifier,
        delivery_date=problem.delivery_date,
        nodes=nodes,
        vehicles=split.vehicles,
        customers={i: problem.customers[code] for i, code in enumerate(nodes) if i},
        distance=distances,
        cost=costs,
        valid_ijk=tuple(costs),
        outgoing={key: tuple(values) for key, values in outgoing.items()},
        incoming={key: tuple(values) for key, values in incoming.items()},
        fixed_vehicle_cost=problem.fixed_vehicle_cost,
        currency=problem.currency,
        diagnostics=problem.diagnostics,
    )
    InstanceValidator().validate(data)
    return data
