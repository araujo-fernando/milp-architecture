from __future__ import annotations

import argparse
import json
from pathlib import Path

from .instrumentation import configure_logging, log_execution_time
from .pipeline import CVRPPipeline


@log_execution_time
def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Resolve uma instância CVRP em JSON.")
    parser.add_argument("input", type=Path)
    parser.add_argument("cd")
    parser.add_argument("--date")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = CVRPPipeline(json.loads(args.input.read_text(encoding="utf-8")), args.cd, args.date).run()
    text = json.dumps(result, ensure_ascii=False, indent=4)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
