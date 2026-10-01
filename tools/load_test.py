#!/usr/bin/env python3
"""Send the same request many times and report how the service held up.

The tool is not the lesson. We do not want to spend the session building a
benchmarking framework, so this stays small and leans on the standard library:
nothing to `pip install`, nothing to learn but the numbers it prints.

What it gives us is exactly two controls and one report:

  --requests     how much total work to send
  --concurrency  how many of those requests are allowed to overlap at once

Concurrency is the knob that matters in Session 7. At --concurrency 1 the
requests are strictly sequential: we are measuring one request's latency with
no contention. Raise it and requests start to overlap, so we can watch what the
*single* API instance does when several callers arrive at the same time.

Example:

    python tools/load_test.py \\
        --url http://localhost:8000/users/501 \\
        --requests 100 \\
        --concurrency 1

Output shape:

    requests:   100
    successes:  100
    failures:   0
    RPS:        42.3
    p50:        18 ms
    p95:        31 ms
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True)
class Attempt:
    """One request's result. latency_ms is set whether or not it succeeded, so
    a slow error still shows up in the percentiles rather than vanishing."""

    ok: bool
    latency_ms: float


@dataclass(frozen=True)
class Report:
    requests: int
    successes: int
    failures: int
    rps: float
    p50_ms: float
    p95_ms: float


def send_once(url: str, method: str, timeout: float) -> Attempt:
    """Send one request and time it end to end.

    A 2xx is a success; everything else — 4xx, 5xx, a timeout, a refused
    connection — is a failure. We deliberately do not read or validate the body:
    this measures the service's ability to answer under load, not correctness,
    which the test suite already covers.
    """
    request = urllib.request.Request(url, method=method)
    started = perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
        ok = True
    except urllib.error.HTTPError:
        # The server answered, just not with a 2xx. That is still a completed
        # round trip, so the latency is meaningful; the status is not a success.
        ok = False
    except (urllib.error.URLError, TimeoutError, OSError):
        # No usable answer at all: timeout, connection refused, DNS, reset.
        ok = False
    latency_ms = (perf_counter() - started) * 1000
    return Attempt(ok=ok, latency_ms=latency_ms)


def percentile(sorted_ms: list[float], pct: float) -> float:
    """Nearest-rank percentile over an already-sorted list.

    Nearest-rank (rather than interpolating between samples) keeps the result a
    latency we actually observed, which is easier to reason about when teaching:
    "95% of requests finished in this many ms or less" is literally true.
    """
    if not sorted_ms:
        return 0.0
    rank = max(1, -(-len(sorted_ms) * pct // 100))  # ceil(len * pct / 100)
    return sorted_ms[int(rank) - 1]


def run_load(url: str, requests: int, concurrency: int, method: str, timeout: float) -> Report:
    """Fire `requests` requests through a pool of `concurrency` workers.

    The pool size *is* the overlap: at most `concurrency` requests are ever in
    flight, and a worker only picks up the next one when its current request
    finishes. RPS is measured over the wall-clock span of the whole run, so it
    already reflects whatever queuing that overlap caused.
    """
    attempts: list[Attempt] = []
    wall_start = perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(send_once, url, method, timeout) for _ in range(requests)]
        for future in futures:
            attempts.append(future.result())
    wall_elapsed = perf_counter() - wall_start

    successes = sum(1 for a in attempts if a.ok)
    latencies = sorted(a.latency_ms for a in attempts)
    # Guard the degenerate case: an instant run should not report infinite RPS.
    rps = requests / wall_elapsed if wall_elapsed > 0 else 0.0

    return Report(
        requests=requests,
        successes=successes,
        failures=requests - successes,
        rps=rps,
        p50_ms=percentile(latencies, 50),
        p95_ms=percentile(latencies, 95),
    )


def format_report(report: Report) -> str:
    # Fixed two-column layout so the numbers line up when read aloud in session.
    return "\n".join(
        [
            f"requests:   {report.requests}",
            f"successes:  {report.successes}",
            f"failures:   {report.failures}",
            f"RPS:        {report.rps:.1f}",
            f"p50:        {report.p50_ms:.0f} ms",
            f"p95:        {report.p95_ms:.0f} ms",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send the same request repeatedly and report RPS and latency percentiles.",
    )
    parser.add_argument("--url", required=True, help="full URL to hit, e.g. http://localhost:8000/users/501")
    parser.add_argument("--requests", type=int, default=100, help="total number of requests to send")
    parser.add_argument("--concurrency", type=int, default=1, help="how many requests may overlap at once")
    parser.add_argument("--method", default="GET", help="HTTP method (default: GET)")
    parser.add_argument("--timeout", type=float, default=10.0, help="per-request timeout in seconds")
    args = parser.parse_args(argv)

    if args.requests < 1:
        parser.error("--requests must be at least 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    if args.concurrency > args.requests:
        # More workers than work is harmless but misleading, so cap it and say so.
        print(
            f"note: --concurrency {args.concurrency} > --requests {args.requests}, "
            f"capping concurrency to {args.requests}",
            file=sys.stderr,
        )
        args.concurrency = args.requests
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_load(
        url=args.url,
        requests=args.requests,
        concurrency=args.concurrency,
        method=args.method.upper(),
        timeout=args.timeout,
    )
    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
