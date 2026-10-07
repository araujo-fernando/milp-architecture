"""Pipeline enxuto para construir e resolver instâncias CVRP."""

from .config import PipelineConfig
from .domain import InstanceData, ProblemData, Route, RoutingSolution
from .model import CVRPBuilderCplex, CVRPBuilderDocplex
from .pipeline import CVRPPipeline
from .transform import InstanceTransformer

__all__ = [
    "CVRPBuilderCplex",
    "CVRPBuilderDocplex",
    "CVRPPipeline",
    "InstanceData",
    "InstanceTransformer",
    "PipelineConfig",
    "ProblemData",
    "Route",
    "RoutingSolution",
]
