"""Interrupções simuladas determinísticas sem depender da velocidade do solver."""

from pathlib import Path
from time import perf_counter

import pytest

from benchmark import create_input
from cvrp import InstanceTransformer, PipelineConfig
from cvrp.domain.results import ModelSolution, StageResult
from cvrp.solve.lexicographic import LexicographicSolver


class FakeBuilder:
    def __init__(self, first, second):
        self.first = first
        self.second = second
        self.limit = None
        self.exports = []
        self.calls = []
        self.closed = False

    def build(self):
        return self

    def freeze_cost(self, value):
        self.limit = value

    def minimize_balance(self):
        pass

    def export(self, path):
        self.exports.append(path.name)

    def close(self):
        self.closed = True

    def solve_stage(self, objective, seconds, split_id):
        self.calls.append((objective, seconds))
        chosen = self.first if objective == "cost" else self.second
        if isinstance(chosen, Exception):
            raise chosen
        return StageResult(split_id, objective, "time limit", None, None, None, 0, chosen is not None), chosen


def runner(first, second, **options):
    data = InstanceTransformer(create_input(1, 1), "CD-BENCH").transform()
    solver = LexicographicSolver(data, PipelineConfig(**options))
    solver.builder.close()
    solver.builder = FakeBuilder(first, second)
    return solver


@pytest.mark.parametrize(
    "second", [None, RuntimeError("runtime failed"), ModelSolution((), 10, 2), ModelSolution((), 11, 0)]
)
def test_second_failure_or_worse_result_keeps_first(second):
    first = ModelSolution((), 10, 0)
    solver = runner(first, second)
    assert solver.run("split") == first
    assert solver.cost_limit == pytest.approx(10.000001)
    assert any(d.code == "fo2_fallback" for d in solver.diagnostics)
    if isinstance(second, RuntimeError):
        assert solver.stages[-1].status == "failed"
        assert any(d.code == "fo2_failed" for d in solver.diagnostics)
    solver.close()
    assert solver.builder.closed


def test_lower_cost_preserves_lexicography_even_if_balance_changes():
    first, second = ModelSolution((), 10, 0), ModelSolution((), 9, 2)
    solver = runner(first, second)
    assert solver.run("split") == second
    assert tuple(stage.objective for stage in solver.stages) == ("cost", "balance")


def test_first_without_incumbent_does_not_run_second():
    solver = runner(None, ModelSolution((), 10, 0))
    assert solver.run("split") is None
    assert len(solver.stages) == 1
    assert solver.cost_limit is None


def test_budget_exhausted_before_first_does_not_invoke_solver():
    solver = runner(ModelSolution((), 10, 0), None)
    assert solver.run("split", perf_counter() - 1) is None
    assert solver.stages[0].status == "budget_exhausted"
    assert not solver.builder.calls


def test_shared_budget_exports_both_stages(tmp_path):
    first, second = ModelSolution((), 10, 2), ModelSolution((), 10, 0)
    solver = runner(first, second, solve_seconds=10, export_lp=True, output_dir=Path(tmp_path))
    assert solver.run("split", artifacts=tmp_path) == second
    assert solver.builder.exports == ["fo1.lp", "fo2.lp"]
    assert solver.builder.calls[0][1] == pytest.approx(7)
    assert solver.builder.calls[1][1] <= 10
