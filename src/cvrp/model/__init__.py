"""Construção estática do modelo de otimização."""

from .builder import CVRPBuilderCplex, CVRPBuilderDocplex

__all__ = ["CVRPBuilderCplex", "CVRPBuilderDocplex"]
