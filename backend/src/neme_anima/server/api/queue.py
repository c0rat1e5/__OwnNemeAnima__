"""
server/api/queue.py — 抽出ジョブのキュー操作。

エンドポイント:
  POST /api/projects/{slug}/extract        → 抽出開始
  POST /api/projects/{slug}/rerun          → 閾値変更後の再実行
  GET  /api/jobs                           → 全ジョブ一覧
  GET  /api/jobs/{job_id}                  → ジョブ詳細
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["queue"])


class ExtractRequest(BaseModel):
    source_idx: int


class RerunRequest(BaseModel):
    source_idx: int
    video: str | None = None  # ビデオ stem で絞り込む場合


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


@router.post("/api/projects/{slug}/extract", status_code=202)
async def start_extract(slug: str, body: ExtractRequest, request: Request) -> dict:
    """指定ソースの抽出パイプラインをキューに積む。
    
    即座に job_id を返す。進捗は /api/events (SSE) で受け取る。
    """
    registry = request.app.state.registry
    if registry.get(slug) is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")
    job_id = request.app.state.queue.enqueue("extract", {
        "project_slug": slug,
        "source_idx": body.source_idx,
    })
    return {"job_id": job_id}


@router.post("/api/projects/{slug}/rerun", status_code=202)
async def start_rerun(slug: str, body: RerunRequest, request: Request) -> dict:
    """閾値を変えたあとの再実行 (検出・追跡はキャッシュを使う)。"""
    registry = request.app.state.registry
    if registry.get(slug) is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")
    job_id = request.app.state.queue.enqueue("rerun", {
        "project_slug": slug,
        "source_idx": body.source_idx,
        "video": body.video,
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
