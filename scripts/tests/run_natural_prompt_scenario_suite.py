from __future__ import annotations

import sys
from pathlib import Path

from run_natural_prompt_pair_suite import main


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_SHEET = ROOT / "backend" / "evals" / "natural_prompt_scenario_cases.json"
DEFAULT_SCENARIO_OUTPUT_DIR = ROOT / "temp" / "natural-prompt-scenarios"


def _ensure_default_arg(flag: str, value: Path) -> None:
    if flag in sys.argv:
        return
    sys.argv.extend([flag, str(value)])


if __name__ == "__main__":
    _ensure_default_arg("--sheet", DEFAULT_SCENARIO_SHEET)
    _ensure_default_arg("--output-dir", DEFAULT_SCENARIO_OUTPUT_DIR)
    sys.exit(main())
