"""Tests for the load generator's pure logic.

We do not test against a live server here — the network path is what the tool
measures, not what we assert on. What has real logic worth pinning down is the
percentile maths and how an attempt mix becomes a report.
"""

from __future__ import annotations

import sys
from pathlib import Path

# tools/ is a sibling of app/, not a package, so make it importable directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pytest  # noqa: E402

import load_test  # noqa: E402


@pytest.mark.parametrize(
    "values, pct, expected",
    [
        ([10], 50, 10),
        ([10], 95, 10),
        (list(range(1, 101)), 50, 50),  # nearest-rank: ceil(100*50/100)=50 -> values[49]=50
        (list(range(1, 101)), 95, 95),
        ([5, 1, 3, 2, 4], 50, 3),  # caller sorts, but check a mid value lands right
    ],
)
def test_percentile_nearest_rank(values, pct, expected):
    assert load_test.percentile(sorted(values), pct) == expected


def test_percentile_empty_is_zero():
    assert load_test.percentile([], 95) == 0.0


def test_report_counts_failures(monkeypatch):
    # Alternate ok/failed attempts so successes and failures are both exercised
    # without touching the network.
    calls = iter(
        [
            load_test.Attempt(ok=True, latency_ms=10.0),
            load_test.Attempt(ok=False, latency_ms=20.0),
            load_test.Attempt(ok=True, latency_ms=30.0),
            load_test.Attempt(ok=False, latency_ms=40.0),
        ]
    )
    monkeypatch.setattr(load_test, "send_once", lambda *a, **k: next(calls))

    report = load_test.run_load(url="http://x", requests=4, concurrency=2, method="GET", timeout=1.0)

    assert report.requests == 4
    assert report.successes == 2
    assert report.failures == 2
    assert report.rps > 0
    assert report.p95_ms == 40.0


def test_parse_args_caps_concurrency_to_requests():
    args = load_test.parse_args(["--url", "http://x", "--requests", "5", "--concurrency", "50"])
    assert args.concurrency == 5


def test_parse_args_rejects_zero_requests():
    with pytest.raises(SystemExit):
        load_test.parse_args(["--url", "http://x", "--requests", "0"])
