"""
server/api/frames.py — kept フレームのアップロード・表示・タグ編集・移動。

エンドポイント:
  POST   /api/projects/{slug}/frames              → 画像アップロード (kept/ に保存)
  GET    /api/projects/{slug}/frames              → フレーム一覧 (metadata.jsonl から)
  GET    /api/projects/{slug}/frames/{filename}   → 画像ファイル配信
  PATCH  /api/projects/{slug}/frames/{filename}   → タグ/キャプション編集
  DELETE /api/projects/{slug}/frames/{filename}   → フレーム削除 (reject に移動)
  POST   /api/projects/{slug}/frames/{filename}/move → 別キャラクターに移動
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects/{slug}/frames", tags=["frames"])


def _get_project(request: Request, slug: str):
    project = request.app.state.registry.get(slug)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")
    return project


def _load_metadata(project) -> list[dict[str, Any]]:
    """metadata.jsonl を読み込んで全行を返す。"""
    if not project.metadata_path.exists():
        return []
    rows = []
    with open(project.metadata_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def _save_metadata(project, rows: list[dict[str, Any]]) -> None:
    """metadata.jsonl を全行書き直す。"""
    with open(project.metadata_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


class PatchFrameRequest(BaseModel):
    tags: list[str] | None = None
    caption: str | None = None
    character_slug: str | None = None


class MoveFrameRequest(BaseModel):
    character_slug: str


@router.post("", status_code=201)
async def upload_frame(
    slug: str,
    request: Request,
    file: UploadFile = File(...),
    character_slug: str | None = None,
) -> dict:
    """PNG 画像を kept/ にアップロードして metadata.jsonl に登録する。

    同名ファイルが既に存在する場合は UUID サフィックスで区別する。
    character_slug が省略された場合はプロジェクトの最初のキャラクターを使用。
    """
    project = _get_project(request, slug)

    # ファイル名の検証 + 重複回避
    original_name = Path(file.filename or "upload.png").name
    if not original_name.lower().endswith(".png"):
        raise HTTPException(status_code=400, detail="PNG ファイルのみ受け付けます")

    dest = project.kept_dir / original_name
    if dest.exists():
        stem = Path(original_name).stem
        dest = project.kept_dir / f"{stem}-{uuid.uuid4().hex[:8]}.png"

    # キャラクター確認
    char = project._resolve_character(character_slug)

    data = await file.read()
    dest.write_bytes(data)

    # metadata.jsonl に追記
    row: dict[str, Any] = {
        "filename": dest.name,
        "character_slug": char.slug,
        "tags": [],
        "caption": "",
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(project.metadata_path, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return row


@router.get("")
async def list_frames(
    slug: str,
    request: Request,
    character_slug: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    """kept フレームの一覧を返す。character_slug または tag でフィルタ可能。"""
    project = _get_project(request, slug)
    rows = _load_metadata(project)

    # フィルタリング
    if character_slug:
        rows = [r for r in rows if r.get("character_slug") == character_slug]
    if tag:
        rows = [r for r in rows if tag in r.get("tags", [])]

    return rows


@router.get("/{filename}")
async def get_frame_image(slug: str, filename: str, request: Request) -> FileResponse:
    """フレーム画像ファイルを返す。"""
    project = _get_project(request, slug)
    # セキュリティ: パストラバーサルを防ぐ
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = project.kept_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="frame not found")
    return FileResponse(path)


@router.patch("/{filename}")
async def patch_frame(
    slug: str, filename: str, body: PatchFrameRequest, request: Request
) -> dict:
    """フレームのタグ・キャプション・キャラクター割り当てを更新する。"""
    project = _get_project(request, slug)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    rows = _load_metadata(project)
    target = next((r for r in rows if r.get("filename") == filename), None)
    if target is None:
        raise HTTPException(status_code=404, detail="frame not found in metadata")

    if body.tags is not None:
        target["tags"] = body.tags
        # .txt ファイルも更新する (kohya-ss 形式)
        txt_path = project.kept_dir / (Path(filename).stem + ".txt")
        txt_path.write_text(", ".join(body.tags))

    if body.caption is not None:
        target["caption"] = body.caption

    if body.character_slug is not None:
        if project.character_by_slug(body.character_slug) is None:
            raise HTTPException(
                status_code=400,
                detail=f"character not found: {body.character_slug}",
            )
        target["character_slug"] = body.character_slug

    _save_metadata(project, rows)
    return target


@router.delete("/{filename}", status_code=204)
async def delete_frame(slug: str, filename: str, request: Request) -> None:
    """フレームを kept から rejected に移動し、metadata から除外する。"""
    project = _get_project(request, slug)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    src = project.kept_dir / filename
    if not src.is_file():
        raise HTTPException(status_code=404, detail="frame not found")

    # rejected に移動
    dst = project.rejected_dir / filename
    shutil.move(str(src), str(dst))

    # .txt も移動
    txt_src = project.kept_dir / (Path(filename).stem + ".txt")
    if txt_src.is_file():
        shutil.move(str(txt_src), str(project.rejected_dir / txt_src.name))

    # metadata から除外
    rows = _load_metadata(project)
    rows = [r for r in rows if r.get("filename") != filename]
    _save_metadata(project, rows)


@router.post("/{filename}/move")
async def move_frame(
    slug: str, filename: str, body: MoveFrameRequest, request: Request
) -> dict:
    """フレームを別のキャラクターに再割り当てする。"""
    project = _get_project(request, slug)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    if project.character_by_slug(body.character_slug) is None:
        raise HTTPException(
            status_code=400, detail=f"character not found: {body.character_slug}"
        )

    rows = _load_metadata(project)
    target = next((r for r in rows if r.get("filename") == filename), None)
    if target is None:
        raise HTTPException(status_code=404, detail="frame not found in metadata")

    target["character_slug"] = body.character_slug
    _save_metadata(project, rows)
    return target
