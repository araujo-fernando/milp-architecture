"""Logging e medição de tempo da aplicação."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from time import perf_counter
from typing import Any, Self, cast

from rich.logging import RichHandler


@dataclass
class _ExecutionMeasurement:
    """Mede e registra a duração de um bloco de execução."""

    name: str
    elapsed_seconds: float = field(init=False, default=0.0)
    _started_at: float = field(init=False, repr=False)

    def __enter__(self) -> Self:
        Instrumentation.info("Iniciando %s", self.name)
        self._started_at = perf_counter()
        return self

    def __exit__(self, *_: object) -> bool:
        self.elapsed_seconds = perf_counter() - self._started_at
        Instrumentation.info("Finalizando %s em %.4f segundos", self.name, self.elapsed_seconds)
        return False


class Instrumentation:
    """Ponto único para logs e medição de duração da aplicação."""

    _LOGGER_NAME = "cvrp"

    @classmethod
    def configure(cls, log_path: Path = Path("execution.log"), *, force: bool = False) -> None:
        """Configura logs para o terminal e para o arquivo de execução."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(cls._LOGGER_NAME)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if logger.handlers and not force:
            return
        if force:
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()

        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        console_handler = RichHandler(rich_tracebacks=True, show_path=False)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    @classmethod
    def _logger(cls) -> logging.Logger:
        logger = logging.getLogger(cls._LOGGER_NAME)
        if not logger.handlers:
            cls.configure()
        return logger

    @classmethod
    def debug(cls, message: str, *args: object, **kwargs: object) -> None:
        cls._logger().debug(message, *args, **kwargs)

    @classmethod
    def info(cls, message: str, *args: object, **kwargs: object) -> None:
        cls._logger().info(message, *args, **kwargs)

    @classmethod
    def warning(cls, message: str, *args: object, **kwargs: object) -> None:
        cls._logger().warning(message, *args, **kwargs)

    @classmethod
    def error(cls, message: str, *args: object, **kwargs: object) -> None:
        cls._logger().error(message, *args, **kwargs)

    @classmethod
    def exception(cls, message: str, *args: object, **kwargs: object) -> None:
        cls._logger().exception(message, *args, **kwargs)

    @classmethod
    def measure(cls, name: str) -> _ExecutionMeasurement:
        """Retorna um contexto que registra e disponibiliza a duração do bloco."""
        return _ExecutionMeasurement(name)

    @classmethod
    def log_execution_time[F: Callable[..., Any]](cls, function: F) -> F:
        """Decora uma função para registrar sua duração."""

        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with cls.measure(function.__qualname__):
                return function(*args, **kwargs)

        return cast(F, wrapped)


# Aliases mantidos para compatibilidade com consumidores da versão anterior.
configure_logging = Instrumentation.configure
log_execution_time = Instrumentation.log_execution_time
