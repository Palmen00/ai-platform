from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from statistics import fmean


LATENCY_RE = re.compile(r"latency_ms=(?P<latency>\d+(?:\.\d+)?)")


@dataclass
class BackupReport:
    sample_count: int
    average_latency_ms: float
    max_latency_ms: float
    status: str


def parse_latency_lines(lines: list[str]) -> list[float]:
    values: list[float] = []
    for line in lines:
        match = LATENCY_RE.search(line)
        if match:
            values.append(float(match.group("latency")))
    return values


def build_backup_report(lines: list[str]) -> BackupReport:
    latencies = parse_latency_lines(lines)
    if not latencies:
        return BackupReport(
            sample_count=0,
            average_latency_ms=0.0,
            max_latency_ms=0.0,
            status="no_samples",
        )
    max_latency = max(latencies)
    status = "healthy" if max_latency < 1500 else "slow"
    return BackupReport(
        sample_count=len(latencies),
        average_latency_ms=round(fmean(latencies), 1),
        max_latency_ms=round(max_latency, 1),
        status=status,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize backup latency logs.")
    parser.add_argument("logfile")
    args = parser.parse_args()
    with open(args.logfile, encoding="utf-8") as handle:
        report = build_backup_report(handle.readlines())
    print(report)


if __name__ == "__main__":
    main()
