#!/usr/bin/env python3
"""Shensi latency diagnostic: extract phase timings from cloud logs.

Run on the cloud host:
  python3 scripts/diagnose_latency.py

Or with custom paths:
  python3 scripts/diagnose_latency.py --log-dir /home/admin/.hermes/logs --tail 200
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Shensi latency diagnostic")
    p.add_argument(
        "--log-dir",
        default="/home/admin/.hermes/logs",
        help="Path to Hermes log directory",
    )
    p.add_argument(
        "--tail",
        type=int,
        default=200,
        help="Number of lines to read from each log file",
    )
    return p.parse_args()


def tail_lines(path: Path, n: int) -> list[str]:
    """Return the last n lines of a file efficiently."""
    if not path.exists():
        return []
    try:
        with open(path, "rb") as f:
            # Seek to approximate position
            f.seek(0, 2)  # end
            size = f.tell()
            if size == 0:
                return []
            # Read last ~8KB or more to get n lines
            chunk_size = min(size, max(8192, n * 200))
            f.seek(max(0, size - chunk_size))
            raw = f.read().decode("utf-8", errors="replace")
            lines = raw.splitlines()
            if len(lines) > n:
                lines = lines[-n:]
            return lines
    except OSError:
        return []


def parse_elapsed(line: str) -> int | None:
    m = re.search(r"elapsed_ms=(\d+)", line)
    return int(m.group(1)) if m else None


def parse_total_ms(line: str) -> int | None:
    m = re.search(r"total_elapsed_ms=(\d+)", line)
    return int(m.group(1)) if m else None


def parse_phase(line: str) -> str | None:
    m = re.search(r"phase=(\S+)", line)
    return m.group(1) if m else None


def parse_message_id(line: str) -> str:
    m = re.search(r"message_id=(\S+)", line)
    return m.group(1) if m else "unknown"


def fmt_ms(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms/1000:.1f}s"


def analyze_analysis_log(lines: list[str]) -> dict:
    """Parse shensi-feishu-analysis-latest.log"""
    phases: dict[str, list[int]] = defaultdict(list)
    totals: list[int] = []
    errors: list[str] = []

    for line in lines:
        phase = parse_phase(line)
        if not phase:
            continue
        elapsed = parse_elapsed(line)
        total = parse_total_ms(line)

        if total is not None:
            totals.append(total)

        if phase in ("submit_failed",):
            errors.append(line.strip()[-200:])

        if elapsed is not None:
            phases[phase].append(elapsed)

    return {
        "phases": dict(phases),
        "totals": totals,
        "errors": errors,
    }


def analyze_submit_log(lines: list[str]) -> dict:
    """Parse shensi-antigravity-submit.log"""
    phases: dict[str, list[int]] = defaultdict(list)
    totals: list[int] = []
    errors: list[str] = []

    for line in lines:
        phase = parse_phase(line)
        if not phase:
            continue
        elapsed = parse_elapsed(line)
        total = parse_total_ms(line)

        if total is not None:
            totals.append(total)

        if phase in ("vision_failed", "submit_failed", "shensi_post_failed"):
            errors.append(line.strip()[-300:])

        if elapsed is not None:
            phases[phase].append(elapsed)

    return {
        "phases": dict(phases),
        "totals": totals,
        "errors": errors,
    }


def main() -> None:
    args = parse_args()
    log_dir = Path(args.log_dir)

    print("=" * 65)
    print("  Shensi Latency Diagnostic")
    print(f"  log dir : {log_dir}")
    print(f"  tail    : last {args.tail} lines per log")
    print("=" * 65)

    # --- Analysis log ---
    analysis_path = log_dir / "shensi-feishu-analysis-latest.log"
    analysis_lines = tail_lines(analysis_path, args.tail)
    if analysis_lines:
        print(f"\n📋 shensi-feishu-analysis-latest.log  ({len(analysis_lines)} lines)")
        data = analyze_analysis_log(analysis_lines)

        if data["totals"]:
            sorted_totals = sorted(data["totals"])
            print(f"   Total end-to-end (last {len(sorted_totals)} runs):")
            print(f"     min  : {fmt_ms(sorted_totals[0])}")
            print(f"     p50  : {fmt_ms(sorted_totals[len(sorted_totals)//2])}")
            print(f"     p95  : {fmt_ms(sorted_totals[int(len(sorted_totals)*0.95)])}")
            print(f"     max  : {fmt_ms(sorted_totals[-1])}")

        print(f"   Phase breakdown (avg):")
        for phase_name, values in sorted(data["phases"].items()):
            avg = sum(values) // len(values)
            print(f"     {phase_name:30s}  avg {fmt_ms(avg):>8s}  (n={len(values)})")

        if data["errors"]:
            print(f"   ⚠️  Errors ({len(data['errors'])}):")
            for err in data["errors"][-5:]:
                print(f"     {err}")
    else:
        print(f"\n⚠️  {analysis_path} not found or empty")

    # --- Submit log ---
    submit_path = log_dir / "shensi-antigravity-submit.log"
    submit_lines = tail_lines(submit_path, args.tail)
    if submit_lines:
        print(f"\n📋 shensi-antigravity-submit.log  ({len(submit_lines)} lines)")
        data = analyze_submit_log(submit_lines)

        if data["totals"]:
            sorted_totals = sorted(data["totals"])
            print(f"   Total submit wrapper (last {len(sorted_totals)} runs):")
            print(f"     min  : {fmt_ms(sorted_totals[0])}")
            print(f"     p50  : {fmt_ms(sorted_totals[len(sorted_totals)//2])}")
            print(f"     p95  : {fmt_ms(sorted_totals[int(len(sorted_totals)*0.95)])}")
            print(f"     max  : {fmt_ms(sorted_totals[-1])}")

        print(f"   Phase breakdown (avg):")
        for phase_name, values in sorted(data["phases"].items()):
            avg = sum(values) // len(values)
            print(f"     {phase_name:30s}  avg {fmt_ms(avg):>8s}  (n={len(values)})")

        # Show which phase dominates
        vision_done = data["phases"].get("vision_done", [])
        ingest_http = data["phases"].get("ingest_http_done", [])
        if vision_done:
            avg_vision = sum(vision_done) // len(vision_done)
            print(f"\n   🔍 Vision (Antigravity/Gemini) is the dominant phase:")
            print(f"      avg {fmt_ms(avg_vision)} per image")
            if ingest_http:
                avg_ingest = sum(ingest_http) // len(ingest_http)
                print(f"      Shensi ingest API avg {fmt_ms(avg_ingest)}")

        if data["errors"]:
            print(f"\n   ⚠️  Errors ({len(data['errors'])}):")
            for err in data["errors"][-5:]:
                print(f"     {err}")
    else:
        print(f"\n⚠️  {submit_path} not found or empty")

    # --- Card callback log (from Shensi stdout) ---
    print(f"\n📋 Shensi card callback timings (from shensi-api journal):")
    print(f"   Run this on cloud host:")
    print(f"   journalctl -u shensi-api --since '1 hour ago' --no-pager | grep 'phase=card_callback' | tail -30")

    # --- Summary ---
    print(f"\n{'='*65}")
    print(f"  If vision_done > 60s  → Antigravity/Gemini is the bottleneck")
    print(f"  If ingest_http > 5s   → Shensi API is slow (check disk I/O)")
    print(f"  If card_send > 3s     → Feishu API is slow (rate limit?)")
    print(f"  If total < 30s but still feels slow → Hermes LLM or Feishu queue")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
