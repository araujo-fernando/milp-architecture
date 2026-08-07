"""Pipeline enxuto para construir e resolver instâncias CVRP."""

from .domain import InstanceData
from .model import CVRPBuilder
from .pipeline import CVRPPipeline
from .transform import InstanceTransformer

__all__ = ["CVRPBuilder", "CVRPPipeline", "InstanceData", "InstanceTransformer"]
