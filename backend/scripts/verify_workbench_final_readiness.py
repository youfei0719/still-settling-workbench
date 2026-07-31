from __future__ import annotations

import argparse
import json
from pathlib import Path

from workbench_status_report import MARKDOWN_PATH, REPORT_PATH, build_status, write_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Strict final readiness check for Douyin script workbench v1.")
    parser.add_argument("--link", help="Authorized Douyin link or share text for final validation.")
    parser.add_argument("--human-review-file", type=Path, help="Human review JSON file.")
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--markdown", type=Path, default=MARKDOWN_PATH)
    parser.add_argument(
        "--skip-real-link",
        action="store_true",
        help="Do not execute real douyin-downloader validation even when ready.",
    )
    parser.add_argument(
        "--skip-real-model",
        action="store_true",
        help="Do not require real model smoke. This is not a final v1 pass.",
    )
    args = parser.parse_args()

    status_args = argparse.Namespace(
        link=args.link,
        run_link=not args.skip_real_link,
        expect_model=not args.skip_real_model,
        human_review_file=args.human_review_file,
    )
    report = build_status(status_args)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, args.markdown)

    print(
        "workbench_final_readiness "
        f"passed={report['passed']} "
        f"code={report['code_ready']} "
        f"video={report['video_ready']} "
        f"external={report['external_ready']} "
        f"api={'healthy' if report['services']['api']['healthy'] else 'not_healthy'} "
        f"frontend={'healthy' if report['services']['frontend']['healthy'] else 'not_healthy'} "
        f"report={args.report} "
        f"markdown={args.markdown}"
    )
    if not report["passed"]:
        for item in report["remaining"]:
            print(f"- {item}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
