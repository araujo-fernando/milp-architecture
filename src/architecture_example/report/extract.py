"""Adaptador de solução Docplex para o JSON hierárquico documentado."""

from datetime import datetime
from hashlib import sha256
from typing import Any

from architecture_example.domain import InstanceData
from architecture_example.instrumentation import Instrumentation as inst
from architecture_example.model import CVRPBuilder


class SolutionReporter:
    """Extrai a solução para o contrato JSON de saída."""

    def __init__(self, data: InstanceData, builder: CVRPBuilder, solution: Any, build_seconds: float, solve_seconds: float):
        self.data = data
        self.builder = builder
        self.solution = solution
        self.build_seconds = build_seconds
        self.solve_seconds = solve_seconds

    @inst.log_execution_time
    def extract(self) -> dict[str, Any]:
        """Retorna o envelope de execução, KPIs e rotas."""
        values = self.solution.get_value_dict(self.builder.x, keep_zeros=False)
        routes = [_route(self.data, vehicle, values) for vehicle in range(len(self.data.vehicles)) if any(key[2] == vehicle for key in values)]
        total_distance = sum(route["kpis"]["distancia_km"] for route in routes)
        total_load = sum(self.data.demand_kg.values())
        return {"execucao": {"id_execucao": f"RUN-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{self.data.depot}", "instancia": f"{self.data.depot}/{self.data.delivery_date}", "gerado_em": datetime.now().astimezone().isoformat(), "versao_modelo": "cvrp-3idx-1.0.0", "hash_instancia": f"sha256:{sha256(repr(self.data).encode()).hexdigest()[:16]}", "moeda": self.data.currency}, "status_solver": {"status": str(self.solution.solve_status), "objetivo": self.solution.objective_value, "tempo_build_s": round(self.build_seconds, 4), "tempo_solve_s": round(self.solve_seconds, 4), "num_variaveis": self.builder.model.number_of_variables, "num_restricoes": self.builder.model.number_of_constraints}, "instancia_resumo": {"clientes_elegiveis": len(self.data.demand_kg), "clientes_atendidos": len(self.data.demand_kg), "clientes_descartados": list(self.data.discarded), "veiculos_disponiveis": len(self.data.vehicles), "veiculos_utilizados": len(routes), "demanda_total_kg": total_load, "capacidade_total_kg": sum(vehicle.capacity_kg for vehicle in self.data.vehicles)}, "kpis_globais": {"custo_total": self.solution.objective_value, "distancia_total_km": total_distance, "carga_total_kg": total_load, "paradas_total": len(self.data.demand_kg)}, "rotas": routes, "diagnostico": []}


def _route(data: InstanceData, vehicle: int, values: dict[tuple[int, int, int], float]) -> dict[str, Any]:
    arcs = {(i, j): value for (i, j, k), value in values.items() if k == vehicle and value > 0.5}
    sequence, node = [0], 0
    while node in {start for start, _ in arcs}:
        node = next(end for start, end in arcs if start == node)
        sequence.append(node)
        if node == 0:
            break
    distance = sum(data.distance[sequence[i], sequence[i + 1]] for i in range(len(sequence) - 1))
    load = sum(data.demand_kg.get(node, 0) for node in sequence)
    vehicle_data = data.vehicles[vehicle]
    return {"id_rota": vehicle + 1, "veiculo": {"id": vehicle_data.identifier, "tipo": vehicle_data.kind, "capacidade_kg": vehicle_data.capacity_kg, "capacidade_m3": vehicle_data.capacity_m3}, "kpis": {"distancia_km": distance, "carga_kg": load, "ocupacao_kg_pct": 100 * load / vehicle_data.capacity_kg, "num_paradas": len(sequence) - 2}, "paradas": [{"seq": position, "no": data.nodes[node], "tipo": "deposito" if position == 0 else "retorno" if node == 0 else "cliente", "razao_social": data.names.get(node), "demanda_kg": data.demand_kg.get(node, 0.0), "pedidos": list(data.orders.get(node, ()))} for position, node in enumerate(sequence)]}
