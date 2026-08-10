from __future__ import annotations

import argparse
import json
from pathlib import Path

from .instrumentation import Instrumentation as inst
from .pipeline import CVRPPipeline


@inst.log_execution_time
def run(input_path: Path, cd: str, date: str | None, output_path: Path, cplex_log: bool = False) -> None:
    """Resolve the scenario and writes its result alongside the input."""
    result = CVRPPipeline(json.loads(input_path.read_text(encoding="utf-8")), cd, date, cplex_log=cplex_log).run()
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=4), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve uma instância CVRP em um diretório de cenário.")
    parser.add_argument("path", type=Path, help="Diretório do cenário, contendo input.json.")
    parser.add_argument("cd")
    parser.add_argument("--date")
    parser.add_argument("--cplex-log", action="store_true", help="Exibe o log do CPLEX durante a resolução.")
    args = parser.parse_args()

    scenario_path = args.path
    inst.configure(scenario_path / "execution.log", force=True)
    run(scenario_path / "input.json", args.cd, args.date, scenario_path / "output.json", args.cplex_log)


if __name__ == "__main__":
    main()
