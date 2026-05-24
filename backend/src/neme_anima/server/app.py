"""
server/app.py — FastAPI アプリのファクトリー関数。

■ 責務:
  - ProjectRegistry / Broadcaster / JobQueue / TrainingManager を初期化
  - それらを app.state に格納 (各ルートハンドラーから request.app.state で取得)
  - 全 API ルーターを登録
  - フロントエンド (Next.js の静的ビルド) を /static 以下に配信

■ lifespan (起動・停止フック):
  FastAPI 0.95+ の lifespan を使う。
  async with 内の yield 前が「起動処理」、yield 後が「停止処理」。
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from neme_anima.server.events import Broadcaster, Event
from neme_anima.server.job_progress import (
    TAG_STAGES,
    JobProgress,
)
from neme_anima.server.queue import JobQueue
from neme_anima.server.registry import ProjectRegistry

logger = logging.getLogger(__name__)


def default_state_dir() -> Path:
    """デフォルトのサーバー状態ディレクトリ (~/.neme-anima)。"""
    return Path.home() / ".neme-anima"


def _make_pipeline_runner(
    active_progresses: dict[str, JobProgress],
    registry: ProjectRegistry,
    broadcaster: Broadcaster,
):
    """JobQueue が呼ぶランナー関数を作る。

    クロージャーにすることで registry / broadcaster を引数として受け取らずに
    ランナーの中で使えるようにしている。
    """

    def runner(job_id: str, payload: dict) -> None:
        project_slug = str(payload.get("project_slug", ""))
        character_slug = payload.get("character_slug") or None
        retag = bool(payload.get("retag", False))

        project = registry.get(project_slug)
        if project is None:
            logger.error("runner: project not found: %s", project_slug)
            return

        loop = asyncio.get_event_loop()
        progress = JobProgress(
            loop=loop,
            broadcaster=broadcaster,
            job_id=job_id,
            project_slug=project_slug,
            source_idx=0,
            kind="tag",
            stages=TAG_STAGES,
        )
        progress.publish_initial()
        active_progresses[job_id] = progress

        logger.info("pipeline.start job=%s project=%s", job_id, project_slug)

        try:
            from neme_anima.pipeline import run_tag

            run_tag(
                project=project,
                character_slug=character_slug,
                retag=retag,
                progress=progress,
            )
            progress.done()
        except Exception as exc:
            logger.error("pipeline.error job=%s: %s", job_id, exc)
            logger.debug(traceback.format_exc())
            progress.error(str(exc))
            raise
        finally:
            active_progresses.pop(job_id, None)

    return runner


def create_app(*, state_dir: Path | None = None) -> FastAPI:
    """FastAPI アプリを初期化して返す。

    state_dir: サーバー状態 (db.sqlite 等) の保存先。デフォルトは ~/.neme-anima。
    """
    state_dir = state_dir or default_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    registry = ProjectRegistry(state_dir / "db.sqlite")
    broadcaster = Broadcaster()
    active_progresses: dict[str, JobProgress] = {}

    queue = JobQueue(
        runner=_make_pipeline_runner(active_progresses, registry, broadcaster),
    )

    # TrainingManager: 抽出キューとは別の学習専用コーディネーター
    from neme_anima.server.training_runner import TrainingManager

    training_manager = TrainingManager(broadcaster=broadcaster)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await queue.start()
        try:
            yield
        finally:
            await queue.stop()
            await training_manager.shutdown()

    app = FastAPI(title="neme-anima", version="0.1.0", lifespan=lifespan)

    # ────────── app.state に共有リソースを格納 ──────────
    app.state.registry = registry
    app.state.broadcaster = broadcaster
    app.state.queue = queue
    app.state.state_dir = state_dir
    app.state.active_progresses = active_progresses
    app.state.training = training_manager

    # ────────── ヘルスチェック ──────────
    @app.get("/api/health", tags=["health"])
    async def health() -> dict:
        return {"ok": True}

    # ────────── API ルーターを登録 ──────────
    from neme_anima.server.api import projects, characters
    from neme_anima.server.api import frames, queue as queue_router
    from neme_anima.server.api import training, ws

    app.include_router(projects.router)
    app.include_router(characters.router)
    app.include_router(frames.router)
    app.include_router(queue_router.router)
    app.include_router(training.router)
    app.include_router(ws.router)

    # ────────── 静的ファイル (Next.js ビルド成果物) ──────────
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)

    if (static_dir / "_next").exists():
        # Next.js の静的エクスポート (_next/static/ 等) を配信
        app.mount(
            "/_next",
            StaticFiles(directory=static_dir / "_next"),
            name="next-static",
        )

    # SPA フォールバック: /api/* 以外は index.html を返す
    from fastapi.responses import FileResponse

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str = "") -> FileResponse:
        if full_path.startswith("api/"):
            from fastapi import HTTPException

            raise HTTPException(status_code=404)
        index = static_dir / "index.html"
        if not index.exists():
            from fastapi import HTTPException

            raise HTTPException(
                status_code=503,
                detail="Frontend not built yet. Run: cd frontend && npm run build",
            )
        return FileResponse(index)

    return app
