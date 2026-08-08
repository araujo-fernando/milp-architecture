"""Pipeline enxuto para construir e resolver instâncias CVRP."""

from .domain import InstanceData
from .model import CVRPBuilderCplex, CVRPBuilderDocplex
from .pipeline import CVRPPipeline
from .transform import InstanceTransformer

__all__ = ["CVRPBuilderCplex", "CVRPBuilderDocplex", "CVRPPipeline", "InstanceData", "InstanceTransformer"]
