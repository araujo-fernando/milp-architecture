"""Identidade reproduzível do conteúdo e configuração relevante."""

import json
from dataclasses import asdict
from hashlib import sha256
from typing import cast

from cvrp.config import PipelineConfig
from cvrp.domain.instance import ProblemData

from .data import JsonValue


def configuration(config: PipelineConfig) -> dict[str, JsonValue]:
    values = asdict(config)
    for name in ("output_dir", "cplex_log", "export_lp"):
        values.pop(name)
    return cast(dict[str, JsonValue], values)


def canonical_instance(problem: ProblemData, config: PipelineConfig) -> dict[str, JsonValue]:
    return {
        "depot": cast(JsonValue, asdict(problem.depot)),
        "delivery_date": problem.delivery_date,
        "customers": [
            {
                "location": cast(JsonValue, asdict(customer.location)),
                "demand_kg": customer.demand_kg,
                "demand_m3": customer.demand_m3,
                "orders": cast(JsonValue, sorted(customer.orders)),
            }
            for _, customer in sorted(problem.customers.items())
        ],
        "vehicles": [
            cast(JsonValue, asdict(vehicle)) for vehicle in sorted(problem.vehicles, key=lambda v: v.identifier)
        ],
        "travel": {
            "locations": [
                cast(JsonValue, asdict(location)) for _, location in sorted(problem.travel.locations.items())
            ],
            "overrides": [
                {"origin": origin, "destination": destination, "distance": distance}
                for (origin, destination), distance in sorted(problem.travel.overrides.items())
            ],
            "blocked": {
                kind: cast(JsonValue, sorted(identifiers))
                for kind, identifiers in sorted(problem.travel.blocked.items())
            },
            "mode": problem.travel.mode,
        },
        "fixed_vehicle_cost": problem.fixed_vehicle_cost,
        "currency": problem.currency,
        "configuration": configuration(config),
    }


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def instance_hash(problem: ProblemData, config: PipelineConfig) -> str:
    return "sha256:" + sha256(compact_json(canonical_instance(problem, config)).encode("utf-8")).hexdigest()
