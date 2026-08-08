"""Fronteira de validação: dados crus para `InstanceData`."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

from architecture_example.domain import InstanceData, Vehicle
from architecture_example.instrumentation import Instrumentation as inst


class InputError(ValueError):
    """Dados de entrada que não permitem construir uma instância confiável."""


class InstanceTransformer:
    """Transforma um JSON bruto em uma instância CVRP validada."""

    def __init__(self, raw: dict[str, Any], cd: str, delivery_date: str | None = None):
        self.raw = raw
        self.cd = cd
        self.delivery_date = delivery_date or raw["metadata"]["data_referencia"]

    @inst.log_execution_time
    def transform(self) -> InstanceData:
        """Retorna a instância concreta pronta para o builder."""
        depot = _find_by_code(self.raw["centros_distribuicao"], self.cd)
        return self._transform(depot)

    def _transform(self, depot: dict[str, Any]) -> InstanceData:
        raw, cd, date = self.raw, self.cd, self.delivery_date
        if not depot["ativo"]:
            raise InputError(f"CD inativo: {cd}")
        products = {item["sku"]: item for item in raw["catalogo_produtos"]}
        clients = {item["codigo"]: item for item in raw["clientes"]}
        demand, orders, discarded = _aggregate_orders(raw["pedidos"], clients, products, cd, date)
        eligible = {code: clients[code] for code in demand if _has_coordinates(clients[code])}
        for code in set(demand) - set(eligible):
            discarded.append({"codigo": code, "motivo": "coordenada_ausente"})
            demand.pop(code), orders.pop(code)
        vehicles = _expand_vehicles(raw, cd)
        if not vehicles:
            raise InputError(f"Nenhum veículo disponível para {cd}")
        _validate_capacity(demand, vehicles)
        nodes = (cd, *sorted(eligible))
        node_index = {code: index for index, code in enumerate(nodes)}
        distance = _distances(nodes, depot, eligible, raw.get("distancias_conhecidas", []))
        valid, cost = _arcs(nodes, distance, vehicles, _blocked_clients(raw.get("restricoes_circulacao", []), cd))
        missing = [code for code in eligible if not any(j == node_index[code] for _, j, _ in valid)]
        if missing:
            raise InputError(f"Clientes sem arco de chegada: {', '.join(missing)}")
        return InstanceData(cd, date, nodes, vehicles, {node_index[c]: d[0] for c, d in demand.items()}, {node_index[c]: d[1] for c, d in demand.items()}, {node_index[c]: tuple(v) for c, v in orders.items()}, {node_index[c]: v["razao_social"] for c, v in eligible.items()}, distance, cost, frozenset(valid), raw["parametros_operacionais"]["custo_fixo_por_veiculo"], raw["parametros_operacionais"]["moeda"], tuple(discarded))


def _find_by_code(items: list[dict[str, Any]], code: str) -> dict[str, Any]:
    for item in items:
        if item["codigo"] == code:
            return item
    raise InputError(f"Código não encontrado: {code}")


def _aggregate_orders(orders: list[dict[str, Any]], clients: dict[str, Any], products: dict[str, Any], cd: str, date: str) -> tuple[dict[str, tuple[float, float]], dict[str, list[str]], list[dict[str, str]]]:
    result: dict[str, tuple[float, float]] = {}
    references: dict[str, list[str]] = {}
    discarded: list[dict[str, str]] = []
    seen: set[str] = set()
    for order in orders:
        if order["numero"] in seen:
            continue
        seen.add(order["numero"])
        if order["status"] != "CONFIRMADO" or order["data_entrega"] != date:
            continue
        client = clients.get(order["cliente"])
        if client is None:
            discarded.append({"codigo": order["cliente"], "motivo": "cliente_nao_cadastrado"})
            continue
        if client["cd_atendimento"] != cd:
            continue
        kg, m3 = _order_load(order["itens"], products)
        old_kg, old_m3 = result.get(order["cliente"], (0.0, 0.0))
        result[order["cliente"]] = old_kg + kg, old_m3 + m3
        references.setdefault(order["cliente"], []).append(order["numero"])
    return result, references, discarded


def _order_load(items: list[dict[str, Any]], products: dict[str, Any]) -> tuple[float, float]:
    kg = m3 = 0.0
    for item in items:
        product = products.get(item["sku"])
        if product is None:
            raise InputError(f"SKU ausente no catálogo: {item['sku']}")
        kg += item["quantidade_caixas"] * product["peso_kg_caixa"]
        m3 += item["quantidade_caixas"] * product["volume_m3_caixa"]
    return kg, m3


def _has_coordinates(item: dict[str, Any]) -> bool:
    return item["latitude"] is not None and item["longitude"] is not None


def _expand_vehicles(raw: dict[str, Any], cd: str) -> tuple[Vehicle, ...]:
    kinds = {item["codigo"]: item for item in raw["frota"]["tipos"]}
    unit_cost = raw["parametros_operacionais"]["custo_por_km"]
    vehicles = []
    for available in raw["frota"]["disponibilidade"]:
        if available["cd"] == cd:
            kind = kinds[available["tipo"]]
            vehicles.extend(Vehicle(f"{kind['codigo']}-{cd}-{number + 1:02d}", kind["codigo"], kind["capacidade_kg"], kind["capacidade_m3"], unit_cost * kind["custo_km_relativo"]) for number in range(available["quantidade"] - available["em_manutencao"]))
    return tuple(vehicles)


def _validate_capacity(demand: dict[str, tuple[float, float]], vehicles: tuple[Vehicle, ...]) -> None:
    loads = list(demand.values())
    if any(kg > max(v.capacity_kg for v in vehicles) or m3 > max(v.capacity_m3 for v in vehicles) for kg, m3 in loads):
        raise InputError("A demanda de um cliente excede a capacidade de todos os veículos")
    if sum(load[0] for load in loads) > sum(v.capacity_kg for v in vehicles):
        raise InputError("Capacidade total em kg insuficiente")
    if sum(load[1] for load in loads) > sum(v.capacity_m3 for v in vehicles):
        raise InputError("Capacidade total em m³ insuficiente")


def _distances(nodes: tuple[str, ...], depot: dict[str, Any], clients: dict[str, Any], overrides: list[dict[str, Any]]) -> dict[tuple[int, int], float]:
    places = {nodes[0]: depot, **clients}
    known = {(item["origem"], item["destino"]): item["distancia_km"] for item in overrides}
    return {(i, j): known.get((origin, destination), _haversine(places[origin], places[destination])) for i, origin in enumerate(nodes) for j, destination in enumerate(nodes) if i != j}


def _haversine(origin: dict[str, Any], destination: dict[str, Any]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (origin["latitude"], origin["longitude"], destination["latitude"], destination["longitude"]))
    return 6371.0 * 2 * asin(sqrt(sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2))


def _blocked_clients(rules: list[dict[str, Any]], cd: str) -> dict[str, set[str]]:
    blocked: dict[str, set[str]] = {}
    for rule in rules:
        if rule["cd"] == cd:
            blocked.setdefault(rule["tipo_veiculo"], set()).update(rule["clientes_bloqueados"])
    return blocked


def _arcs(nodes: tuple[str, ...], distance: dict[tuple[int, int], float], vehicles: tuple[Vehicle, ...], blocked: dict[str, set[str]]) -> tuple[set[tuple[int, int, int]], dict[tuple[int, int, int], float]]:
    valid, cost = set(), {}
    for k, vehicle in enumerate(vehicles):
        for (i, j), km in distance.items():
            if nodes[i] not in blocked.get(vehicle.kind, set()) and nodes[j] not in blocked.get(vehicle.kind, set()):
                valid.add((i, j, k))
                cost[i, j, k] = km * vehicle.cost_per_km
    return valid, cost
