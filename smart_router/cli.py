from __future__ import annotations

import importlib
import sys
from typing import Callable


CommandHandler = Callable[[list[str] | None], int]

COMMANDS: dict[str, tuple[str, str, str]] = {
    "serve": (
        "smart_router.entrypoints.serve.api_server",
        "main",
        "Run the Smart Router API server.",
    ),
    "benchmark": (
        "smart_router.entrypoints.benchmark.benchmark_serving_multi_turn",
        "cli",
        "Run the multi-turn benchmark workload.",
    ),
}


def _print_help() -> None:
    print("Usage: smart-router <command> [args]\n")
    print("Commands:")
    for name, (_, _, description) in COMMANDS.items():
        print(f"  {name:<10} {description}")


def _load_handler(command: str) -> CommandHandler:
    module_path, function_name, _ = COMMANDS[command]
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        if command == "benchmark":
            missing_pkg = exc.name or "benchmark dependency"
            raise RuntimeError(
                "Benchmark dependencies are not installed "
                f"(missing: {missing_pkg}). Install with `pip install .[benchmark]`."
            ) from exc
        raise
    handler = getattr(module, function_name, None)
    if handler is None:
        raise RuntimeError(
            f"Command handler `{function_name}` was not found in `{module_path}`."
        )
    return handler


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in {"-h", "--help", "help"}:
        _print_help()
        return 0

    command, *command_argv = argv
    if command not in COMMANDS:
        print(f"Unknown command: {command}\n", file=sys.stderr)
        _print_help()
        return 2

    try:
        handler = _load_handler(command)
        return int(handler(command_argv) or 0)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

