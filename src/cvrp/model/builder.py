"""Imports compatíveis; as formulações vivem nos módulos específicos."""

from .builder_cplex import CVRPBuilderCplex
from .builder_docplex import CVRPBuilderDocplex

__all__ = ["CVRPBuilderCplex", "CVRPBuilderDocplex"]
