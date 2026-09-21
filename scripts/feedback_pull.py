#!/usr/bin/env python3
"""Pull the week's feedback and pulse from unwindwords.com into docs/feedback/.

Usage:
    ADMIN_KEY=... python scripts/feedback_pull.py [--base https://unwindwords.com] [--days 7]

Writes docs/feedback/YYYY-WW.md (the markdown digest the skill reads) and
docs/feedback/YYYY-WW.pulse.json (signups, page views, plans, battery and A/B aggregates).
Nothing here needs a model; it is plain HTTP so the rollup skill starts from facts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def get(base: str, path: str, key: str, **params) -> bytes:
    q = urllib.parse.urlencode({"key": key, **{k: v for k, v in params.items() if v is not None}})
    with urllib.request.urlopen(f"{base}{path}?{q}", timeout=30) as r:  # noqa: S310 - our own API
        return r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("UNWIND_BASE", "https://unwindwords.com"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", default="docs/feedback")
    args = ap.parse_args()
    key = os.environ.get("ADMIN_KEY")
    if not key:
        print("ADMIN_KEY is not set (it is the Fly secret of the same name).", file=sys.stderr)
        return 2

    since = (dt.datetime.now(dt.UTC) - dt.timedelta(days=args.days)).isoformat(timespec="seconds")
    week = dt.date.today().strftime("%G-W%V")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    digest = get(args.base, "/api/admin/feedback", key, since=since, format="md").decode()
    summary = json.loads(get(args.base, "/api/admin/feedback/summary", key))
    pulse = json.loads(get(args.base, "/api/admin/export", key))

    md = out / f"{week}.md"
    md.write_text(
        f"# Feedback digest — {week} (last {args.days} days, pulled {dt.date.today()})\n\n"
        f"Summary: {json.dumps(summary['last_7d'])}\n\n" + digest,
        encoding="utf-8",
    )
    (out / f"{week}.pulse.json").write_text(json.dumps(pulse, indent=1), encoding="utf-8")
    print(f"wrote {md} and {md.with_suffix('.pulse.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
