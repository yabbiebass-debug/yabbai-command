#!/usr/bin/env python3
"""
Back up the measured history to timestamped JSON.

    python scripts/backup_db.py
    python scripts/backup_db.py --keep 30
    python scripts/backup_db.py --out D:/backups/yabbai

WHY THIS EXISTS

Everything this project has measured lives in one local MongoDB with no replica
and no snapshot. Price and treasury observations are the one class of data that
cannot be rebuilt: they are readings of a moment that has passed. Lose them and
`/api/performance` has nothing to measure until the poller accumulates weeks of
new history, and the honest answer to "how has the treasury done" becomes "no
idea" for a month.

Deliberately JSON rather than `mongodump`. BSON dumps need the matching tooling
to read, and the tooling is not on this machine — `mongodump` is absent from the
portable zip in mongodb/. A JSON file can be read by anything, forever, including
by hand. Slower and larger, and worth it for an archive whose whole purpose is
being readable later under unknown conditions.

Collections are backed up by value, not by importance ranking, with one
exception: `agent_cycles` is skipped by default. It holds 230,000+ documents that
have produced no income and no measurement anyone reads. Pass --all to include it.

Not a substitute for Atlas backups once this runs anywhere but a laptop.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import pymongo
    from bson import ObjectId
except ImportError:
    sys.exit("pymongo is required:  pip install pymongo")

ROOT = Path(__file__).resolve().parent.parent

# Loaded so this works from a bare checkout with no shell environment set up.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except ImportError:
    pass

# Churn. Regenerated constantly, read by nobody, and 230k documents of it.
NOISY = {"agent_cycles"}


def encode(value):
    """JSON has no ObjectId and no datetime. Preserve both losslessly."""
    if isinstance(value, ObjectId):
        return {"$oid": str(value)}
    if isinstance(value, datetime):
        return {"$date": value.isoformat()}
    raise TypeError(f"cannot encode {type(value).__name__}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Back up measured history to JSON.")
    ap.add_argument("--out", default=str(ROOT / "backups"), help="output directory")
    ap.add_argument("--keep", type=int, default=14, help="how many backups to retain")
    ap.add_argument("--all", action="store_true", help="include high-churn collections")
    args = ap.parse_args()

    mongo_url = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
    db_name = os.environ.get("DB_NAME", "yabbai_local")

    try:
        client = pymongo.MongoClient(mongo_url, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
    except Exception as e:
        print(f"cannot reach MongoDB at {mongo_url}: {e}")
        print("Start it first, or set MONGO_URL.")
        return 1

    db = client[db_name]
    names = sorted(db.list_collection_names())
    if not names:
        print(f"database '{db_name}' has no collections — wrong DB_NAME?")
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / stamp
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"database : {db_name}")
    print(f"target   : {outdir}")
    print("-" * 58)

    manifest, total = {}, 0
    for name in names:
        count = db[name].count_documents({})

        if name in NOISY and not args.all:
            print(f"  {name:<24} {count:>8}  SKIPPED (--all to include)")
            manifest[name] = {"documents": count, "skipped": True}
            continue

        # Streamed, not loaded whole. agent_cycles alone will not fit comfortably
        # in memory as a Python list, and the point of a backup is that it works
        # on the bad day rather than the good one.
        path = outdir / f"{name}.json.gz"
        written = 0
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write("[\n")
            for i, doc in enumerate(db[name].find()):
                if i:
                    fh.write(",\n")
                fh.write(json.dumps(doc, default=encode))
                written += 1
            fh.write("\n]\n")

        size_kb = path.stat().st_size / 1024
        print(f"  {name:<24} {written:>8}  {size_kb:>8.1f} KB")
        manifest[name] = {"documents": written, "bytes": path.stat().st_size}
        total += written

    (outdir / "manifest.json").write_text(
        json.dumps(
            {
                "database": db_name,
                "taken_utc": datetime.now(timezone.utc).isoformat(),
                "total_documents": total,
                "collections": manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("-" * 58)
    print(f"  {total} documents written")

    # Retention. Directory names sort chronologically because the stamp is
    # ISO-ordered, which is the entire reason for that format.
    root = Path(args.out)
    backups = sorted([d for d in root.iterdir() if d.is_dir()], reverse=True)
    for old in backups[args.keep:]:
        for f in old.iterdir():
            f.unlink()
        old.rmdir()
        print(f"  pruned {old.name}")

    print(f"\n{len(backups[:args.keep])} backup(s) retained in {root}")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
