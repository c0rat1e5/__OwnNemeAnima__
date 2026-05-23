"""
server/api/sources.py — ビデオソースの追加・削除・セグメント編集。

エンドポイント:
  GET    /api/projects/{slug}/sources              → ソース一覧
  POST   /api/projects/{slug}/sources              → ビデオ追加 (パス指定)
  DELETE /api/projects/{slug}/sources/{idx}        → ソース削除
  PATCH  /api/projects/{slug}/sources/{idx}/segments → 時間範囲セグメント更新
  PATCH  /api/projects/{slug}/sources/{idx}/excluded-refs → 除外参照更新
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from neme_anima.storage.project import Segment

router = APIRouter(prefix="/api/projects/{slug}/sources", tags=["sources"])


def _get_project(request: Request, slug: str):
    project = request.app.state.registry.get(slug)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")
    return project


def _source_view(source, idx: int) -> dict[str, Any]:
    return {
        "idx": idx,
        "path": source.path,
        "added_at": source.added_at,
        "excluded_refs": source.excluded_refs,
        "extraction_runs": source.extraction_runs,
        "segments": [
            {
                "start_seconds": s.start_seconds,
                "end_seconds": s.end_seconds,
                "label": s.label,
            }
            for s in source.segments
        ],
        "duration_seconds": source.duration_seconds,
        "fps": source.fps,
    }


class AddSourceRequest(BaseModel):
    path: str  # ビデオファイルのフルパス


class SegmentItem(BaseModel):
    start_seconds: float
    end_seconds: float
    label: str = ""


class UpdateSegmentsRequest(BaseModel):
    segments: list[SegmentItem]


class UpdateExcludedRefsRequest(BaseModel):
    character_slug: str | None = None
    excluded: list[str]


@router.get("")
async def list_sources(slug: str, request: Request) -> list[dict]:
    project = _get_project(request, slug)
    return [_source_view(s, i) for i, s in enumerate(project.sources)]


@router.post("", status_code=201)
async def add_source(slug: str, body: AddSourceRequest, request: Request) -> dict:
    project = _get_project(request, slug)
    from pathlib import Path
    try:
        source = project.add_source(Path(body.path))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"file not found: {body.path}")
    idx = project.sources.index(source)
    return _source_view(source, idx)


@router.delete("/{idx}", status_code=204)
async def remove_source(slug: str, idx: int, request: Request) -> None:
    project = _get_project(request, slug)
    if idx < 0 or idx >= len(project.sources):
        raise HTTPException(status_code=404, detail="source not found")
    project.remove_source(idx)


@router.patch("/{idx}/segments")
async def update_segments(
    slug: str, idx: int, body: UpdateSegmentsRequest, request: Request
) -> dict:
    project = _get_project(request, slug)
    if idx < 0 or idx >= len(project.sources):
        raise HTTPException(status_code=404, detail="source not found")
    project.sources[idx].segments = [
        Segment(
            start_seconds=s.start_seconds,
            end_seconds=s.end_seconds,
            label=s.label,
        )
        for s in body.segments
    ]
    project.save()
    return _source_view(project.sources[idx], idx)


@router.patch("/{idx}/excluded-refs")
async def update_excluded_refs(
    slug: str, idx: int, body: UpdateExcludedRefsRequest, request: Request
) -> dict:
    project = _get_project(request, slug)
    if idx < 0 or idx >= len(project.sources):
        raise HTTPException(status_code=404, detail="source not found")
    project.set_excluded_refs(
        idx, body.excluded, character_slug=body.character_slug
    )
    return _source_view(project.sources[idx], idx)
