"""Instrumentação de execução e configuração de logs da aplicação."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from time import perf_counter
from typing import Any, cast

from rich.logging import RichHandler


def configure_logging(log_path: Path = Path("outputs/execution.log")) -> None:
    """Configura logs para o terminal e para o arquivo de execução."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("architecture_example")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = RichHandler(rich_tracebacks=True, show_path=False)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


def log_execution_time[F: Callable[..., Any]](function: F) -> F:
    """Registra o início e a duração da chamada de uma função."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        logger = logging.getLogger("architecture_example")
        if not logger.handlers:
            configure_logging()
        function_name = function.__qualname__
        logger.info("Iniciando %s", function_name)
        started = perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            logger.info("Finalizando %s em %.4f segundos", function_name, perf_counter() - started)

    return cast(F, wrapped)
