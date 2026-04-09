import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smart_router import cli


def test_cli_help_lists_available_commands(capsys):
    assert cli.main([]) == 0
    captured = capsys.readouterr()
    assert "serve" in captured.out
    assert "benchmark" in captured.out


def test_cli_rejects_unknown_command(capsys):
    assert cli.main(["unknown-command"]) == 2
    captured = capsys.readouterr()
    assert "Unknown command" in captured.err


def test_cli_dispatches_to_benchmark_handler(monkeypatch):
    benchmark_calls: list[list[str]] = []

    def fake_import_module(name: str):
        assert name == "smart_router.entrypoints.benchmark.benchmark_serving_multi_turn"
        return type(
            "BenchmarkModule",
            (),
            {"cli": staticmethod(lambda argv=None: benchmark_calls.append(argv or []) or 0)},
        )

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    assert cli.main(["benchmark", "--help"]) == 0
    assert benchmark_calls == [["--help"]]
