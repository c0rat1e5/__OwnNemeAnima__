"""
server/api/characters.py — キャラクターの追加・削除・コピー。

エンドポイント:
  POST   /api/projects/{slug}/characters
  DELETE /api/projects/{slug}/characters/{char_slug}
  POST   /api/projects/{slug}/characters/{char_slug}/copy-to
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects/{slug}/characters", tags=["characters"])


def _get_project(request: Request, slug: str):
    project = request.app.state.registry.get(slug)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")
    return project


class AddCharacterRequest(BaseModel):
    name: str
    slug: str | None = None


class CopyToRequest(BaseModel):
    """このキャラクターを別プロジェクトにコピーする。"""
    target_project_slug: str
    new_name: str | None = None


@router.post("", status_code=201)
async def add_character(slug: str, body: AddCharacterRequest, request: Request) -> dict:
    """プロジェクトに新しいキャラクターを追加する。"""
    project = _get_project(request, slug)
    char = project.add_character(name=body.name, slug=body.slug)
    return {"slug": char.slug, "name": char.name, "trigger_token": char.trigger_token}


@router.delete("/{char_slug}", status_code=204)
async def remove_character(slug: str, char_slug: str, request: Request) -> None:
    """キャラクターを削除する (最後の 1 人は削除不可)。"""
    project = _get_project(request, slug)
    try:
        project.remove_character(char_slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"character not found: {char_slug}")


@router.post("/{char_slug}/copy-to", status_code=201)
async def copy_character_to(
    slug: str, char_slug: str, body: CopyToRequest, request: Request
) -> dict:
    """このキャラクターの参照画像を別プロジェクトにコピーして追加する。"""
    registry = request.app.state.registry
    src_project = _get_project(request, slug)
    dst_project = registry.get(body.target_project_slug)
    if dst_project is None:
        raise HTTPException(
            status_code=404,
            detail=f"target project not found: {body.target_project_slug}",
        )

    src_char = src_project.character_by_slug(char_slug)
    if src_char is None:
        raise HTTPException(status_code=404, detail=f"character not found: {char_slug}")

    # 新キャラクターを追加
    new_name = body.new_name or src_char.name
    new_char = dst_project.add_character(name=new_name)

    # 参照画像をコピー
    for ref in src_char.refs:
        src_path = Path(ref.path)
        if src_path.is_file():
            dst_project.add_ref_bytes(
                src_path.name,
                src_path.read_bytes(),
                character_slug=new_char.slug,
            )

    return {"slug": new_char.slug, "name": new_char.name}
