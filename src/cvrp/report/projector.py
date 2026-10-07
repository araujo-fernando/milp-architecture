"""Projeção de rotas auditadas, sem dependência do solver."""

from datetime import UTC, datetime
from uuid import uuid4

from cvrp.config import PipelineConfig
from cvrp.domain.instance import ProblemData
from cvrp.domain.results import Route, RoutingSolution, SplitResult
from cvrp.validation.solution import route_metrics

from .canonical import compact_json, configuration, instance_hash
from .data import DiagnosticRow, ObjectiveRow, ReportData, RouteRow, SplitRow, StopRow, SummaryRow

SCHEMA_VERSION = "2.0.0"


def new_run_id() -> str:
    return f"RUN-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex}"


class ReportProjector:
    def __init__(
        self, problem: ProblemData | None, solution: RoutingSolution, config: PipelineConfig, *, instance: str = ""
    ) -> None:
        self.problem = problem
        self.instance = instance
        self.solution = solution
        self.config = config
        self.run_id = solution.run_id or new_run_id()
        self.generated_at = datetime.now(UTC).isoformat()
        self._report: ReportData | None = None

    def project(self) -> ReportData:
        if self._report is None:
            routes = tuple(self._route(index, route) for index, route in enumerate(self.solution.routes, 1))
            stops = tuple(
                stop for index, route in enumerate(self.solution.routes, 1) for stop in self._stops(index, route)
            )
            diagnostics = dict.fromkeys(
                (
                    *(self.problem.diagnostics if self.problem else ()),
                    *self.solution.diagnostics,
                    *(d for split, _, _ in self._all_splits() for d in split.diagnostics),
                )
            )
            self._report = ReportData(
                (self._summary(routes),),
                routes,
                stops,
                self._objectives(),
                self._splits(),
                tuple(DiagnosticRow(d.code, d.message, d.entity, d.split_id, d.level) for d in diagnostics),
            )
        return self._report

    def _route(self, identifier: int, route: Route) -> RouteRow:
        assert self.problem is not None
        vehicle = next(v for v in self.problem.vehicles if v.identifier == route.vehicle_id)
        metrics = route_metrics(self.problem, route)
        return RouteRow(
            identifier,
            vehicle.identifier,
            vehicle.kind,
            vehicle.capacity_kg,
            vehicle.capacity_m3,
            metrics.distance_km,
            metrics.load_kg,
            metrics.load_m3,
            metrics.fixed_cost,
            metrics.variable_cost,
            metrics.total_cost,
            100 * metrics.load_kg / vehicle.capacity_kg,
            100 * metrics.load_m3 / vehicle.capacity_m3,
            metrics.stops,
        )

    def _stops(self, identifier: int, route: Route) -> tuple[StopRow, ...]:
        assert self.problem is not None
        vehicle = next(v for v in self.problem.vehicles if v.identifier == route.vehicle_id)
        nodes = (self.problem.depot.identifier, *route.customers, self.problem.depot.identifier)
        rows: list[StopRow] = []
        cumulative = 0.0
        for sequence, node in enumerate(nodes):
            customer = self.problem.customers.get(node)
            location = customer.location if customer else self.problem.depot
            distance = self.problem.travel.distance(nodes[sequence - 1], node) if sequence else 0.0
            cumulative += distance
            kind = "cliente" if customer else "retorno" if sequence else "deposito"
            rows.append(
                StopRow(
                    identifier,
                    route.vehicle_id,
                    sequence,
                    node,
                    kind,
                    location.name,
                    customer.demand_kg if customer else 0.0,
                    customer.demand_m3 if customer else 0.0,
                    customer.orders if customer else (),
                    distance,
                    cumulative,
                    distance * vehicle.cost_per_km,
                )
            )
        return tuple(rows)

    def _objectives(self) -> tuple[ObjectiveRow, ...]:
        return tuple(
            ObjectiveRow(
                stage.split_id,
                index,
                stage.objective,
                stage.status,
                stage.value,
                stage.bound,
                stage.gap,
                stage.seconds,
                stage.has_incumbent,
                stage.proven_optimal,
                stage.cost,
                stage.balance,
                split.cost_limit,
                attempt,
                final,
            )
            for split, attempt, final in self._all_splits()
            for index, stage in enumerate(split.stages, 1)
        )

    def _splits(self) -> tuple[SplitRow, ...]:
        return tuple(
            SplitRow(
                split.split_id,
                split.status,
                split.customer_ids,
                split.vehicle_ids,
                len({customer for route in split.routes for customer in route.customers}),
                len(split.routes),
                split.build_seconds,
                split.variable_count,
                split.constraint_count,
                split.nonzero_count,
                split.cost_limit,
                attempt,
                final,
            )
            for split, attempt, final in self._all_splits()
        )

    def _all_splits(self) -> tuple[tuple[SplitResult, str, bool], ...]:
        return tuple((split, "anterior", False) for split in self.solution.attempts) + tuple(
            (split, "final", True) for split in self.solution.splits
        )

    def _failure_summary(self) -> SummaryRow:
        return SummaryRow(
            self.run_id,
            self.generated_at,
            "",
            SCHEMA_VERSION,
            self.instance,
            "",
            self.config.backend,
            self.solution.status,
            0,
            0,
            0,
            0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0,
            0.0,
            0.0,
            0.0,
            0,
            0,
            0,
            compact_json(configuration(self.config)),
            "{}",
            "null",
        )

    def _summary(self, routes: tuple[RouteRow, ...]) -> SummaryRow:
        problem, solution = self.problem, self.solution
        if problem is None:
            return self._failure_summary()
        cost = sum(route.custo_total for route in routes)
        stops = tuple(route.num_paradas for route in routes if route.num_paradas)
        balance = float(max(stops) - min(stops)) if stops else 0.0
        post = self._postprocess()
        return SummaryRow(
            self.run_id,
            self.generated_at,
            instance_hash(problem, self.config),
            SCHEMA_VERSION,
            f"{problem.depot.identifier}/{problem.delivery_date}",
            problem.currency,
            self.config.backend,
            solution.status,
            len(problem.customers),
            len({c for r in solution.routes for c in r.customers}),
            len(problem.vehicles),
            len(routes),
            sum(c.demand_kg for c in problem.customers.values()),
            sum(c.demand_m3 for c in problem.customers.values()),
            sum(v.capacity_kg for v in problem.vehicles),
            sum(v.capacity_m3 for v in problem.vehicles),
            cost,
            sum(r.custo_fixo for r in routes),
            sum(r.custo_variavel for r in routes),
            sum(r.distancia_km for r in routes),
            sum(r.carga_kg for r in routes),
            sum(r.carga_m3 for r in routes),
            sum(r.num_paradas for r in routes),
            balance,
            sum(s.build_seconds for s, _, _ in self._all_splits()),
            sum(t.seconds for s, _, _ in self._all_splits() for t in s.stages),
            sum(s.variable_count for s in solution.splits),
            sum(s.constraint_count for s in solution.splits),
            sum(s.nonzero_count for s in solution.splits),
            compact_json(configuration(self.config)),
            compact_json(solution.timings),
            compact_json(post),
        )

    def _postprocess(self) -> dict[str, object] | None:
        if self.solution.postprocess is None:
            return None
        post = self.solution.postprocess
        return {
            "cost_before": post.cost_before,
            "cost_after": post.cost_after,
            "balance_before": post.balance_before,
            "balance_after": post.balance_after,
            "seconds": post.seconds,
            "accepted_moves": post.accepted_moves,
            "candidates": post.candidates,
            "stop_reason": post.stop_reason,
        }

    def output(self) -> dict[str, object]:
        report = self.project()
        summary = report.resumo[0].record()
        stops_by_route: dict[int, list[dict[str, object]]] = {}
        for stop in report.paradas:
            record: dict[str, object] = {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in stop.record().items()
                if key not in {"id_rota", "veiculo_id"}
            }
            stops_by_route.setdefault(stop.id_rota, []).append(record)
        route_outputs: list[dict[str, object]] = []
        for route in report.rotas:
            route_outputs.append(
                {
                    "id_rota": route.id_rota,
                    "veiculo": {
                        "id": route.veiculo_id,
                        "tipo": route.tipo_veiculo,
                        "capacidade_kg": route.capacidade_kg,
                        "capacidade_m3": route.capacidade_m3,
                    },
                    "kpis": {
                        key: value
                        for key, value in route.record().items()
                        if key not in {"id_rota", "veiculo_id", "tipo_veiculo", "capacidade_kg", "capacidade_m3"}
                    },
                    "paradas": stops_by_route.get(route.id_rota, []),
                }
            )
        return {
            "execucao": {
                "versao_modelo": "cvrp-mtz-2.0.0",
                **{
                    key: summary[key]
                    for key in ("id_execucao", "instancia", "gerado_em", "hash_instancia", "moeda", "versao_schema")
                },
            },
            "status_solver": {
                "status": self.solution.status,
                "objetivo": summary["custo_total"],
                **{
                    key: summary[key]
                    for key in ("tempo_build_s", "tempo_solve_s", "num_variaveis", "num_restricoes", "num_nao_zeros")
                },
            },
            "instancia_resumo": {
                **{
                    key: summary[key]
                    for key in (
                        "clientes_elegiveis",
                        "clientes_atendidos",
                        "veiculos_disponiveis",
                        "veiculos_utilizados",
                        "demanda_total_kg",
                        "demanda_total_m3",
                        "capacidade_total_kg",
                        "capacidade_total_m3",
                    )
                },
                "clientes_descartados": [
                    {"codigo": d.entity, "motivo": d.code}
                    for d in (self.problem.diagnostics if self.problem else ())
                    if d.code in {"coordenada_ausente", "cliente_nao_cadastrado"}
                ],
            },
            "kpis_globais": {
                key: summary[key]
                for key in (
                    "custo_total",
                    "custo_fixo",
                    "custo_variavel",
                    "distancia_total_km",
                    "carga_total_kg",
                    "carga_total_m3",
                    "paradas_total",
                    "equilibrio_paradas",
                )
            },
            "rotas": route_outputs,
            "diagnostico": [row.record() for row in report.diagnostico],
            "objetivos": [row.record() for row in report.objetivos],
            "splits": [row.record() for row in report.splits],
            "pos_processamento": self._postprocess(),
            "tempos": dict(self.solution.timings),
        }
