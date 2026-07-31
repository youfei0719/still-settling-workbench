from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
REPORT_PATH = ROOT / "evals" / "workbench" / "external-gates-report.json"
HUMAN_REVIEW_TEMPLATE = ROOT / "evals" / "workbench" / "human-review-template.json"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("WORKBENCH_DB_MODE", "off")

from app.script_workbench import (  # noqa: E402
    external_link_gate as backend_external_link_gate,
    external_llm_gate as backend_external_llm_gate,
    human_review_gate as backend_human_review_gate,
    write_human_review_template,
)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    if args.write_human_review_template:
        write_human_review_template(HUMAN_REVIEW_TEMPLATE)
    link = backend_external_link_gate(args.link, args.run_link)
    llm = backend_external_llm_gate(args.expect_model)
    human = backend_human_review_gate(args.human_review_file)
    return {
        "passed": link["passed"] and llm["passed"] and human["passed"],
        "link_gate": link,
        "llm_gate": llm,
        "human_review_gate": human,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify external gates for the Douyin script workbench v1.")
    parser.add_argument("--link", help="Authorized Douyin link or share text for real link validation.")
    parser.add_argument("--run-link", action="store_true", help="Actually run douyin-downloader for the provided link.")
    parser.add_argument("--expect-model", action="store_true", help="Require real LLM credentials and model mode.")
    parser.add_argument("--human-review-file", type=Path, help="JSON file with 10 manually reviewed hotspot scripts.")
    parser.add_argument("--write-human-review-template", action="store_true", help="Write a human review JSON template.")
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()

    report = build_report(args)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "workbench_external_gates "
        f"passed={report['passed']} "
        f"link={report['link_gate']['status']} "
        f"llm={report['llm_gate']['status']} "
        f"human={report['human_review_gate']['status']} "
        f"report={args.report}"
    )
    if not report["passed"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
