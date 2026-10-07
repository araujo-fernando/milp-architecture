"""Contratos tipados usados nas etapas do pipeline."""

from .instance import Customer, InstanceData, Location, ProblemData, ProblemSplit, TravelData, Vehicle
from .results import Diagnostic, Route, RoutingSolution

__all__ = [
    "Customer",
    "Diagnostic",
    "InstanceData",
    "Location",
    "ProblemData",
    "ProblemSplit",
    "Route",
    "RoutingSolution",
    "TravelData",
    "Vehicle",
]
