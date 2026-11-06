"""Evaluate an explicit, private ASDOS handwriting manifest without reading PDFs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.asdos_domain.evaluation import EvaluationInputError, evaluate_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Path to a private JSON evaluation manifest")
    parser.add_argument("--split", required=True, choices=("development", "calibration", "locked_test"))
    parser.add_argument("--output", type=Path, help="Optional path for an aggregate JSON report")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = evaluate_manifest(manifest, split=args.split)
    except (OSError, json.JSONDecodeError, EvaluationInputError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
