"""K-means local e reserva exclusiva de frota, com fallback conservador."""

from math import cos, radians

from sklearn.cluster import KMeans

from cvrp.config import PipelineConfig
from cvrp.domain.instance import ProblemData, ProblemSplit, Vehicle
from cvrp.domain.results import Diagnostic
from cvrp.validation.instance import eligible


class ClusterPreprocessor:
    def __init__(self) -> None:
        self.diagnostics: tuple[Diagnostic, ...] = ()

    def split(self, problem: ProblemData, config: PipelineConfig) -> tuple[ProblemSplit, ...]:
        self.diagnostics = ()
        clients = tuple(sorted(problem.customers))
        if not clients:
            return ()
        points = self._project(problem, clients)
        usable = tuple(v for v in problem.vehicles if any(eligible(problem, problem.customers[c], v) for c in clients))
        count = min(config.clusters, len(clients), len(set(points)), len(usable))
        if count < config.clusters:
            self._diagnose("clusters_reduzidos", f"Clusters limitados de {config.clusters} para {max(1, count)}")
        for size in range(count, 1, -1):
            groups = self._groups(clients, points, size, config.seed)
            splits = self._allocate(problem, groups, usable)
            if splits is not None:
                self.validate_splits(problem, splits)
                return splits
            self._diagnose(
                "alocacao_frota_falhou",
                f"Reserva gulosa falhou com {size} clusters; não prova inviabilidade de packing; reagrupar",
            )
        result = (ProblemSplit("split_001", clients, problem.vehicles),)
        self.validate_splits(problem, result)
        if config.clusters > 1:
            self._diagnose(
                "fallback_problema_unico", "Resolver problema único com toda a frota; partição não prova inviabilidade"
            )
        return result

    @staticmethod
    def _project(problem: ProblemData, clients: tuple[str, ...]) -> tuple[tuple[float, float], ...]:
        """Projeção equiretangular em km: aproximação para operações regionais.

        Usa latitude média e longitude relativa ao depósito, normalizada no
        antimeridiano. Não substitui distâncias geodésicas do roteamento.
        """
        latitude = sum(problem.customers[c].location.latitude for c in clients) / len(clients)
        longitude = problem.depot.longitude
        return tuple(
            (
                6371.0
                * radians((problem.customers[c].location.longitude - longitude + 180) % 360 - 180)
                * cos(radians(latitude)),
                6371.0 * radians(problem.customers[c].location.latitude - latitude),
            )
            for c in clients
        )

    @staticmethod
    def _groups(
        clients: tuple[str, ...], points: tuple[tuple[float, float], ...], count: int, seed: int
    ) -> tuple[tuple[str, ...], ...]:
        labels = KMeans(n_clusters=count, random_state=seed, n_init=10).fit_predict(points)
        groups = tuple(tuple(c for c, label in zip(clients, labels, strict=True) if label == i) for i in range(count))
        return tuple(sorted(group for group in groups if group))

    def _allocate(
        self, problem: ProblemData, groups: tuple[tuple[str, ...], ...], vehicles: tuple[Vehicle, ...]
    ) -> tuple[ProblemSplit, ...] | None:
        compatible = {
            c: tuple(v.identifier for v in vehicles if eligible(problem, problem.customers[c], v))
            for group in groups
            for c in group
        }
        order = sorted(range(len(groups)), key=lambda i: (min(len(compatible[c]) for c in groups[i]), groups[i]))
        owners: dict[str, int] = {}
        loads: dict[str, tuple[float, float]] = {}
        for i in order:
            if not self._reserve_group(problem, groups[i], i, vehicles, compatible, owners, loads):
                return None
        return tuple(
            ProblemSplit(f"split_{i + 1:03d}", group, tuple(v for v in vehicles if owners.get(v.identifier) == i))
            for i, group in enumerate(groups)
        )

    @staticmethod
    def _reserve_group(
        problem: ProblemData,
        group: tuple[str, ...],
        group_index: int,
        vehicles: tuple[Vehicle, ...],
        compatible: dict[str, tuple[str, ...]],
        owners: dict[str, int],
        loads: dict[str, tuple[float, float]],
    ) -> bool:
        clients = sorted(
            group,
            key=lambda c: (len(compatible[c]), -problem.customers[c].demand_kg, -problem.customers[c].demand_m3, c),
        )
        for client in clients:
            customer = problem.customers[client]
            candidates = tuple(
                v
                for v in vehicles
                if v.identifier in compatible[client]
                and owners.get(v.identifier, group_index) == group_index
                and loads.get(v.identifier, (0, 0))[0] + customer.demand_kg <= v.capacity_kg + 1e-7
                and loads.get(v.identifier, (0, 0))[1] + customer.demand_m3 <= v.capacity_m3 + 1e-7
            )
            if not candidates:
                return False
            chosen = min(
                candidates,
                key=lambda v: (v.identifier not in owners, v.capacity_kg, v.capacity_m3, v.cost_per_km, v.identifier),
            )
            kg, m3 = loads.get(chosen.identifier, (0, 0))
            loads[chosen.identifier] = kg + customer.demand_kg, m3 + customer.demand_m3
            owners[chosen.identifier] = group_index
        return True

    @staticmethod
    def validate_splits(problem: ProblemData, splits: tuple[ProblemSplit, ...]) -> None:
        identifiers = tuple(split.identifier for split in splits)
        if any(not identifier for identifier in identifiers) or len(identifiers) != len(set(identifiers)):
            raise ValueError("IDs de splits devem ser não vazios e únicos")
        if any(not split.customer_ids for split in splits):
            raise ValueError("Split vazio deve ser omitido")
        clients = tuple(c for split in splits for c in split.customer_ids)
        vehicles = tuple(v.identifier for split in splits for v in split.vehicles)
        fleet = {v.identifier: v for v in problem.vehicles}
        if len(clients) != len(set(clients)) or set(clients) != set(problem.customers):
            raise ValueError("Splits devem formar uma partição completa dos clientes")
        if len(vehicles) != len(set(vehicles)) or not set(vehicles).issubset(v.identifier for v in problem.vehicles):
            raise ValueError("Frota dos splits deve ser exclusiva e pertencer ao problema")
        if any(vehicle != fleet.get(vehicle.identifier) for split in splits for vehicle in split.vehicles):
            raise ValueError("Veículo do split difere do veículo canônico")
        for split in splits:
            ClusterPreprocessor._validate_capacity(problem, split)

    @staticmethod
    def _validate_capacity(problem: ProblemData, split: ProblemSplit) -> None:
        if any(not any(eligible(problem, problem.customers[c], v) for v in split.vehicles) for c in split.customer_ids):
            raise ValueError(f"Split {split.identifier} sem veículo elegível para cada cliente")
        if (
            sum(problem.customers[c].demand_kg for c in split.customer_ids)
            > sum(v.capacity_kg for v in split.vehicles) + 1e-7
        ):
            raise ValueError(f"Split {split.identifier} sem capacidade total em kg")
        if (
            sum(problem.customers[c].demand_m3 for c in split.customer_ids)
            > sum(v.capacity_m3 for v in split.vehicles) + 1e-7
        ):
            raise ValueError(f"Split {split.identifier} sem capacidade total em m³")

    def _diagnose(self, code: str, message: str) -> None:
        self.diagnostics += (Diagnostic(code, message),)
