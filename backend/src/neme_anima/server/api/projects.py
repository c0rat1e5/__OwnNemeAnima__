"""
server/api/projects.py — プロジェクト CRUD エンドポイント。

エンドポイント一覧:
  GET  /api/projects              → 全プロジェクト一覧
  POST /api/projects              → 新規プロジェクト作成
  GET  /api/projects/{slug}       → プロジェクト詳細
  DELETE /api/projects/{slug}     → プロジェクト登録解除 (ファイルは消さない)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from neme_anima.storage.project import Project

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ────────── Pydantic スキーマ ──────────

class CreateProjectRequest(BaseModel):
    """プロジェクト作成リクエスト。
    
    root: プロジェクトフォルダのフルパス (例: "/home/user/neme-projects/megumin")
    name: UI 表示用の名前
    """
    root: str
    name: str


# ────────── レスポンス変換ヘルパー ──────────

def _project_view(project: Project) -> dict[str, Any]:
    """Project オブジェクトを API レスポンス用の dict に変換する。"""
    return {
        "slug": project.slug,
        "name": project.name,
        "root": str(project.root),
        "created_at": project.created_at.isoformat(),
        "characters": [
            {
                "slug": c.slug,
                "name": c.name,
                "trigger_token": c.trigger_token,
                "ref_count": len(c.refs),
            }
            for c in project.characters
        ],
        "source_count": len(project.sources),
        "llm_enabled": project.llm.enabled,
    }


# ────────── エンドポイント ──────────

@router.get("")
async def list_projects(request: Request) -> list[dict]:
    """登録されている全プロジェクトの一覧を返す。"""
    registry = request.app.state.registry
    projects = registry.list_all()
    return [_project_view(p) for p in projects]


@router.post("", status_code=201)
async def create_project(body: CreateProjectRequest, request: Request) -> dict:
    """新しいプロジェクトを作成して登録簿に登録する。"""
    registry = request.app.state.registry
    root = Path(body.root).expanduser().resolve()
    try:
        project = Project.create(root, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    registry.register(project)
    return _project_view(project)


@router.get("/{slug}")
async def get_project(slug: str, request: Request) -> dict:
    """指定した slug のプロジェクト詳細を返す。"""
    registry = request.app.state.registry
    project = registry.get(slug)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")
    return _project_view(project)


@router.delete("/{slug}", status_code=204)
async def delete_project(slug: str, request: Request) -> None:
    """プロジェクトを登録簿から削除する。ディスク上のファイルは消さない。"""
    registry = request.app.state.registry
    if registry.get(slug) is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")
    registry.unregister(slug)


# ────────── Settings (閾値 + LLM) ──────────

class LLMConfigPatch(BaseModel):
    """LLM 設定の部分更新用。"""
    enabled: bool | None = None
    endpoint: str | None = None
    model: str | None = None
    prompt: str | None = None
    api_key: str | None = None


class SettingsPatch(BaseModel):
    """設定の部分更新用。thresholds_json は JSON 文字列として受け取る。"""
    thresholds: dict | None = None   # Thresholds を dict で
    llm: LLMConfigPatch | None = None


@router.get("/{slug}/settings")
async def get_settings(slug: str, request: Request) -> dict:
    """プロジェクトの閾値と LLM 設定を返す。

    ■ 閾値は thresholds.json があればそちら、なければデフォルト値。
    ■ LLM 設定は project.json に保存されている。
    """
    from dataclasses import asdict
    from neme_anima.config import Thresholds

    registry = request.app.state.registry
    project = registry.get(slug)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")

    cfg_path = project.root / "thresholds.json"
    thresholds = Thresholds.from_json(cfg_path) if cfg_path.exists() else Thresholds()

    return {
        "thresholds": asdict(thresholds),
        "llm": {
            "enabled":  project.llm.enabled,
            "endpoint": project.llm.endpoint,
            "model":    project.llm.model,
            "prompt":   project.llm.prompt,
            "api_key":  project.llm.api_key,
        },
    }


@router.patch("/{slug}/settings")
async def patch_settings(
    slug: str, body: SettingsPatch, request: Request
) -> dict:
    """閾値と LLM 設定を更新して保存する。

    thresholds は dict 形式で渡す。知らないキーは無視される (後方互換)。
    llm は部分更新 (None フィールドは変更なし)。
    """
    from dataclasses import asdict
    from neme_anima.config import Thresholds

    registry = request.app.state.registry
    project = registry.get(slug)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")

    # 閾値の更新
    if body.thresholds is not None:
        cfg_path = project.root / "thresholds.json"
        # 既存の値をベースにして上書き (不明キーを _filter_known が除去する)
        import json
        existing = asdict(
            Thresholds.from_json(cfg_path) if cfg_path.exists() else Thresholds()
        )
        # dict をマージ (ネスト 1 段)
        for section, vals in body.thresholds.items():
            if isinstance(vals, dict) and section in existing:
                existing[section].update(vals)
            elif section in existing:
                existing[section] = vals
        cfg_path.write_text(json.dumps(existing, indent=2))
        thresholds = Thresholds.from_json(cfg_path)
    else:
        cfg_path = project.root / "thresholds.json"
        thresholds = Thresholds.from_json(cfg_path) if cfg_path.exists() else Thresholds()

    # LLM 設定の更新
    if body.llm is not None:
        llm = project.llm
        patch = body.llm.model_dump(exclude_none=True)
        for key, val in patch.items():
            setattr(llm, key, val)
        project.save()

    return {
        "thresholds": asdict(thresholds),
        "llm": {
            "enabled":  project.llm.enabled,
            "endpoint": project.llm.endpoint,
            "model":    project.llm.model,
            "prompt":   project.llm.prompt,
            "api_key":  project.llm.api_key,
        },
    }
