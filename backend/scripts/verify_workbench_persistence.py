from __future__ import annotations

import argparse
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine, select

from app.models import WorkbenchGeneratedScript, WorkbenchTemplatePattern
from app.script_workbench import (
    AnalyzeTextRequest,
    GenerateHotspotRequest,
    create_text_analysis,
    generate_hotspot,
)
from app.workbench_persistence import (
    overview_from_database,
    save_analysis_response,
    save_hotspot_response,
)


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")


def build_session(mode: str) -> Session:
    if mode == "sqlite":
        engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(engine)
        return Session(engine)

    from app.core.db import engine

    return Session(engine)


def verify(mode: str, migrate: bool) -> None:
    if migrate:
        if mode != "configured":
            raise ValueError("--migrate 只能和 --mode configured 一起使用")
        run_migrations()

    with build_session(mode) as session:
        analysis = create_text_analysis(
            AnalyzeTextRequest(
                title="持久化验证素材",
                content=(
                    "你以为这只是一次普通回应吗？真正值得看的不是谁赢了，"
                    "而是评论区情绪为什么突然变了。先看公开信息，再看传播结构。"
                ),
            )
        )
        save_analysis_response(session, analysis)

        hotspot = generate_hotspot(
            GenerateHotspotRequest(
                hotspot="某明星公开回应引发粉丝和路人争议",
                account_type="娱乐吃瓜号",
                template_id="tpl_reversal",
            )
        )
        save_hotspot_response(session, hotspot)

        templates = session.exec(select(WorkbenchTemplatePattern)).all()
        scripts = session.exec(select(WorkbenchGeneratedScript)).all()
        overview = overview_from_database(session)

    print(
        "workbench_persistence_ok",
        f"mode={mode}",
        f"templates={len(templates)}",
        f"scripts={len(scripts)}",
        f"overview_templates={len(overview.templates)}",
        f"first_angle={scripts[0].content_angle if scripts else 'none'}",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify workbench persistence.")
    parser.add_argument(
        "--mode",
        choices=["sqlite", "configured"],
        default="sqlite",
        help="sqlite runs an in-memory smoke test; configured uses app.core.config database settings.",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run Alembic migrations before verifying. Only valid with --mode configured.",
    )
    args = parser.parse_args()
    verify(mode=args.mode, migrate=args.migrate)


if __name__ == "__main__":
    main()
