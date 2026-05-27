"""
server/api/queue.py — タグ付けジョブのキュー操作。

エンドポイント:
  POST /api/projects/{slug}/tag  → タグ付け開始
  GET  /api/jobs                 → 全ジョブ一覧
  GET  /api/jobs/{job_id}        → ジョブ詳細
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["queue"])


class TagRequest(BaseModel):
    character_slug: str | None = None        # 対象キャラクター (None = 全画像)
    retag: bool = False                      # 既存タグを上書き
    filenames: list[str] | None = None       # 対象ファイル名リスト (None = 全画像)


def _job_view(job) -> dict:
    return {
        "id": job.id,
        "kind": job.kind,
        "payload": job.payload,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error": job.error,
    }


@router.post("/api/projects/{slug}/tag", status_code=202)
async def start_tag(slug: str, body: TagRequest, request: Request) -> dict:
    """kept/ 内の画像に WD14 タグを付けるジョブをキューに積む。

    即座に job_id を返す。進捗は /api/events (SSE) で受け取る。
    """
    registry = request.app.state.registry
    if registry.get(slug) is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")
    job_id = request.app.state.queue.enqueue("tag", {
        "project_slug": slug,
        "character_slug": body.character_slug,
        "retag": body.retag,
        "filenames": body.filenames,
    })
    return {"job_id": job_id}


@router.get("/api/jobs")
async def list_jobs(request: Request) -> list[dict]:
    """全ジョブの一覧を返す (最新順)。"""
    jobs = request.app.state.queue.list_jobs()
    return [_job_view(j) for j in jobs]


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    """ジョブの詳細を返す。"""
    job = request.app.state.queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return _job_view(job)
