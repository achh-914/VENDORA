"""Runs the offline evaluation as a regression test."""

import importlib.util
from pathlib import Path

EVAL_PATH = Path(__file__).resolve().parents[1] / "eval" / "run_eval.py"


def _load_eval():
    spec = importlib.util.spec_from_file_location("run_eval", EVAL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eval_has_no_failures():
    stats, _, failures = _load_eval().evaluate()
    assert failures == []
    assert stats["detect"] == stats["cases"]
    assert stats["delta"] == stats["delta_n"]


def test_every_fee_case_file_requires_human_approval():
    stats, _, _ = _load_eval().evaluate()
    assert stats["cite_n"] > 0
    assert stats["cite"] == stats["cite_n"]
    assert stats["approval"] == stats["cite_n"]
