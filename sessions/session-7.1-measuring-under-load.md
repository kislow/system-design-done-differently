# Session 7.1 — how much traffic can one instance handle?

We have **one API and one database**. The tempting next step is always "add more servers."
But you can't know if you need more until you know what **one** can do. So before we scale
anything, we measure.

This is the hands-on record of that measurement: what we ran, what came back, and what each
number actually means.

![RPS, percentiles, and the 500 ms latency budget](../diagrams/session7.1-rps-and-percentiles.png)

---

## The tool: `tools/load_test.py`

A load test just means: **send the same request many times on purpose and watch how the
service copes.** Our tool has two knobs and reports three numbers.

**The two knobs:**

| Knob | What it means | Everyday picture |
|------|---------------|------------------|
| `--requests` | how many requests to send in total | how many customers come in today |
| `--concurrency` | how many requests are *in flight at the same time* | how many checkout lanes are open at once |

With `--concurrency 1`, requests go one after another — a single lane, one customer served
at a time. With `--concurrency 10`, ten requests overlap — ten lanes open at once.

**The three numbers it reports:**

- **RPS (requests per second)** — how much work finished each second. This is *throughput*:
  how many meals the kitchen serves per hour. Higher is better.
- **p50 (median latency)** — line up every request from fastest to slowest; p50 is the one
  in the middle. **Half** of requests were faster than this, half slower. This is the
  *typical* experience.
- **p95 (95th-percentile latency)** — **95%** of requests were at least this fast; only the
  slowest **5%** took longer. This is the *unlucky* user's experience.

> Why p95 and not the average? One very slow request can hide inside a nice-looking average.
> p95 is honest about the slow tail — the users who'd actually complain.
>
> Our target this session (from the whiteboard): **95% of requests under 500 ms.** We judge
> against p95, not the average.

---

## Step 0 — check what's running

```
$ docker ps
api-1   uvicorn app.main:app   Up 7 days   :8000
db-1    postgres:16-alpine     Up 7 days (healthy)   :5432
```

One API, one Postgres. Nothing in the request path changes this session — we only put it
under pressure.

---

## Step 1 — read the output correctly (a wrong URL)

First run, pointed at user `501`:

```
$ python tools/load_test.py --url http://localhost:8000/users/501 --requests 100 --concurrency 1

requests:   100
successes:  0
failures:   100
RPS:        214.5
p50:        3 ms
p95:        7 ms
```

**0 successes looks alarming — but the service is fine.** User `501` doesn't exist, so the
API correctly answers `404 Not Found`. Our tool counts anything that isn't a `2xx` as a
"failure," *but it still times the round trip*.

The tell is the speed: **100% failures at 7 ms**. A broken or overloaded server is slow. A
server answering "that user isn't here" in 3 ms is healthy — you just asked for someone who
isn't there. **A 404 is not the API being down.**

Lesson: always read failures *and* latency together before you panic.

---

## Step 2 — a real baseline

Create/confirm a user that exists, then measure it:

```
$ curl -i http://localhost:8000/users/123
HTTP/1.1 200 OK
{"id":123,"name":"john","email":"john@example.com"}

$ python tools/load_test.py --url http://localhost:8000/users/123 --requests 100 --concurrency 1

requests:   100
successes:  100
RPS:        226–248     # ran it twice
p50:        3 ms
p95:        5–8 ms
```

One caller, no overlap. **~3 ms typical, ~5–8 ms for the slow 5%, ~230 requests/sec.** Miles
under our 500 ms budget. This is our reference point — every later run is compared to this.

---

## Step 3 — turn up the overlap

Now let requests overlap and watch the trade-off:

```
$ python tools/load_test.py --url http://localhost:8000/users/123 --requests 300 --concurrency 1
RPS: 259.5   p50: 3 ms    p95: 6 ms    (300/300 ok)

$ python tools/load_test.py --url http://localhost:8000/users/123 --requests 300 --concurrency 10
RPS: 417.1   p50: 20 ms   p95: 45 ms   (300/300 ok)
```

Going from 1 lane to 10:

- **throughput went up** (260 → 417 RPS) — more work finishing each second, good.
- **latency went up too** (p95 6 → 45 ms) — each individual request now waits its turn behind
  others.

This is the fundamental trade-off: **concurrency buys throughput by making each request wait a
bit longer.** Still 100% success, still well under 500 ms. So far, more overlap is a good deal.

---

## Step 4 — push too hard, and it breaks

Crank concurrency to 50:

```
$ python tools/load_test.py --url http://localhost:8000/users/123 --requests 300 --concurrency 50

requests:   300
successes:  4
failures:   296
RPS:        5.0
p50:        10004 ms
p95:        10137 ms
```

This is the moment of the session. We went from **100% success** to **4 out of 300**, and
latency jumped to **~10 seconds**. Two things to explain, and both are the real lesson.

**Why ~10 seconds, exactly?**
That's *our tool's* own patience limit. `load_test.py` waits 10 seconds for each request
(`--timeout`, default 10s) and then gives up. So the 296 "failures" aren't the server saying
"no" — they're requests that **waited and never got served in time**.

**Why did exactly 4 succeed?**
This points straight at a bottleneck. The API talks to Postgres through a **connection pool**
— a small, fixed set of reusable database connections. Think of it as **4 phone lines to the
database**. Each request needs a line for its whole duration.

Our pool has no size configured, so the library's default applies: **4 connections**
(`app/main.py:21`). Send 50 requests at once and only **4 can talk to the database**; the other
46 stand in a queue waiting for a free line — and hit the 10-second cut-off first.

> The wall we hit was **our own 4-connection pool**, not Postgres. `postgres:16-alpine` allows
> **100** connections by default; we never got close. We starved on our own setting.

---

## The whole story in one table

| Concurrency | RPS | p50 | p95 | Success | Verdict |
|------------:|----:|----:|----:|--------:|---------|
| 1  | ~260 | 3 ms | 6 ms | 100% | baseline, fast |
| 10 | ~417 | 20 ms | 45 ms | 100% | more throughput, still fine |
| 50 | ~5 | 10 s | 10 s | 1% | collapsed — pool exhausted |

Somewhere **between 10 and 50** is the point where p95 crosses our 500 ms budget. That number
*is* the real capacity of today's single instance.

---

## What this session proves

1. You can find a single instance's limit with a tiny tool and three numbers — **no scaling,
   no new infrastructure.**
2. Throughput and latency pull against each other as you add concurrency. **Judge p95 against
   your target (500 ms), not the average.**
3. The first bottleneck was an **application setting (pool size 4)** — not CPU, not the
   database, not the network. **Measure before you scale.** If we'd just "added a server," we'd
   have paid for two instances still capped at 4 DB lines each.

---

## Try it yourself

1. Re-run Step 2 and Step 3 — do your numbers roughly match?
2. Binary-search the breaking point: try `--concurrency 20`, then `30`. Where does p95 first
   go past 500 ms?
3. Watch the queue from the database side during a `--concurrency 50` run:
   ```
   docker compose exec db psql -U appuser -d appdb -c "SELECT count(*) FROM pg_stat_activity;"
   ```
4. **Then** fix it deliberately — raise the pool size instead of guessing:
   ```python
   # app/main.py
   pool = ConnectionPool(DATABASE_URL, open=False, max_size=..., timeout=..., connection_timeout=...)
   ```
   Re-measure. Did the collapse move to a higher concurrency? That's you scaling the *right*
   thing, because you measured first.
