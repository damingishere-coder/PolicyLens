from __future__ import annotations

import json
import shutil
import sys
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from policylens_api.domain import ResearchDiscoveryOutput
from policylens_api.research_codex_runner import (
    ARGUMENT_PROFILE,
    ResearchCodexError,
    ResearchCodexRunner,
    discovery_output_schema,
)
from policylens_api.research_progress import ResearchEventTracker

ROOT = Path(__file__).resolve().parents[3]


def test_public_research_runner_uses_search_before_exec_without_provider_overrides(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the synthetic Codex process")
    runner = ResearchCodexRunner(
        tmp_path,
        command=node,
        prefix_args=[str(ROOT / "tests" / "fixtures" / "synthetic" / "fake-research-codex.mjs")],
        timeout_seconds=10,
    )
    result = runner.run()
    assert result["cli_version"] == "codex-cli synthetic-research-1.0"
    assert result["argument_profile"] == ARGUMENT_PROFILE
    assert {item.insurer_id for item in result["result"].products} == {
        "aia-hk",
        "prudential-hk",
    }
    assert result["result"].leads[0].channel == "THIRD_PARTY_LEAD"


def test_schema_requires_nullable_fields_without_weakening_local_validation() -> None:
    schema = discovery_output_schema()
    fact = schema["$defs"]["ResearchDiscoveryFact"]
    assert set(fact["required"]) == set(fact["properties"])
    assert {"type": "null"} in fact["properties"]["unit"]["anyOf"]
    assert "default" not in fact["properties"]["guarantee_type"]
    with pytest.raises(ValidationError):
        ResearchDiscoveryOutput.model_validate(
            {
                "schema_version": "1.0",
                "products": [],
                "leads": [],
                "unexpected": True,
            }
        )


@pytest.mark.parametrize(
    ("diagnostic", "code", "stream"),
    [
        (
            "Not inside a trusted directory and --skip-git-repo-check was not specified.",
            "CODEX_UNTRUSTED_DIRECTORY",
            "stderr",
        ),
        ("Invalid schema: required must include unit", "CODEX_INVALID_SCHEMA", "stdout"),
        ("401 Unauthorized", "CODEX_AUTH_REQUIRED", "stderr"),
        ("You have hit your usage limit", "CODEX_RATE_LIMIT", "stdout"),
        ("error sending request", "CODEX_NETWORK_FAILED", "stderr"),
        ("unrecognized failure", "CODEX_FAILED", "stderr"),
    ],
)
def test_process_failures_keep_safe_reason_and_clean_temporary_files(
    tmp_path: Path,
    diagnostic: str,
    code: str,
    stream: str,
) -> None:
    raw = diagnostic + " synthetic-secret-never-persist"
    message = (
        json.dumps({"type": "turn.failed", "error": {"message": raw}})
        if stream == "stdout"
        else raw
    )
    script = tmp_path / "failing_cli.py"
    script.write_text(
        "import sys\n"
        "if '--version' in sys.argv:\n"
        " print('codex-cli synthetic')\n sys.exit(0)\n"
        f"print({message!r}, file=sys.{stream})\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    runner = ResearchCodexRunner(tmp_path, command=sys.executable, prefix_args=[str(script)])
    with pytest.raises(ResearchCodexError) as caught:
        runner.run()
    assert caught.value.code == code
    assert "synthetic-secret" not in str(caught.value)
    assert list((tmp_path / "temp").iterdir()) == []
    assert runner.cancel() is False


def slow_cli(tmp_path: Path, *, delay: float = 60) -> ResearchCodexRunner:
    script = tmp_path / "slow_cli.py"
    script.write_text(
        "import json, sys, time\nfrom pathlib import Path\n"
        "if '--version' in sys.argv:\n print('codex-cli synthetic-slow')\n sys.exit(0)\n"
        "prompt = sys.stdin.read()\n"
        "assert prompt.count('PolicyLens') == 1\n"
        "print(json.dumps({'type':'turn.started'}), flush=True)\n"
        "print(json.dumps({'type':'item.started','item':{'id':'search_1','type':'web_search','query':'synthetic-secret'}}),flush=True)\n"
        "print(json.dumps({'type':'item.completed','item':{'id':'search_1','type':'web_search','query':'synthetic-secret'}}),flush=True)\n"
        f"time.sleep({delay})\n"
        "Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text(json.dumps({'schema_version':'1.0','products':[],'leads':[]}))\n"
        "print(json.dumps({'type':'turn.completed'}),flush=True)\n",
        encoding="utf-8",
    )
    return ResearchCodexRunner(
        tmp_path, command=sys.executable, prefix_args=[str(script)], timeout_seconds=2
    )


def test_real_process_timeout_retains_safe_progress_and_reaps_child(tmp_path: Path) -> None:
    runner = slow_cli(tmp_path)
    reports = []
    with pytest.raises(ResearchCodexError) as caught:
        runner.run(on_progress=reports.append)
    assert caught.value.code == "CODEX_TIMEOUT"
    assert reports[-1].web_searches == 1
    assert reports[-1].events_observed == 3
    assert reports[-1].elapsed_seconds >= 2
    assert "synthetic-secret" not in reports[-1].model_dump_json()
    assert list((tmp_path / "temp").iterdir()) == []
    assert runner.cancel() is False


def test_polling_sends_prompt_once_and_accepts_completed_result(tmp_path: Path) -> None:
    runner = slow_cli(tmp_path, delay=1.2)
    runner.timeout_seconds = 5
    reports = []
    assert runner.run(on_progress=reports.append)["result"].products == []
    assert reports[-1].phase == "RESPONSE_READY"
    assert reports[-1].web_searches == 1


def test_cancel_during_version_check_does_not_launch_research(tmp_path: Path, monkeypatch) -> None:
    runner = slow_cli(tmp_path)
    checking = threading.Event()
    resume = threading.Event()
    errors = []

    def version():
        checking.set()
        assert resume.wait(5)
        return "codex-cli synthetic"

    def run():
        try:
            runner.run()
        except ResearchCodexError as exc:
            errors.append(exc.code)

    monkeypatch.setattr(runner, "check_version", version)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert checking.wait(5)
        assert runner.cancel() is True
    finally:
        resume.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == ["USER_CANCELLED"]
    assert not (tmp_path / "temp").exists()


def test_cancel_terminates_running_process(tmp_path: Path) -> None:
    runner = slow_cli(tmp_path)
    runner.timeout_seconds = 10
    ready = threading.Event()
    errors = []

    def run():
        try:
            runner.run(on_progress=lambda _progress: ready.set())
        except ResearchCodexError as exc:
            errors.append(exc.code)

    thread = threading.Thread(target=run)
    thread.start()
    assert ready.wait(5)
    assert runner.cancel() is True
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == ["USER_CANCELLED"]
    assert list((tmp_path / "temp").iterdir()) == []


def test_event_tracker_handles_partial_lines_without_retaining_payloads(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'{"type":"turn.sta')
    tracker = ResearchEventTracker()
    tracker.read(path, 1)
    assert tracker.events == 0
    with path.open("ab") as stream:
        stream.write(b'rted"}\ninvalid-json\n{"type":"unknown","secret":"private"}\n')
    tracker.read(path, 2)
    tracker.read(path, 3)
    snapshot = tracker.snapshot(elapsed=3, timeout=900, version="synthetic", profile="synthetic")
    assert snapshot.events_observed == 1
    assert snapshot.last_event_elapsed_seconds == 2
    assert "private" not in snapshot.model_dump_json()
