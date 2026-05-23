"""
server/api/training.py — LoRA 学習の設定・開始・停止。

エンドポイント:
  GET    /api/projects/{slug}/training/config            → 学習設定取得
  PATCH  /api/projects/{slug}/training/config            → 学習設定更新
  POST   /api/projects/{slug}/training/start             → 学習開始
  POST   /api/projects/{slug}/training/stop              → 学習停止
  GET    /api/projects/{slug}/training/status            → 学習状態
  GET    /api/projects/{slug}/training/core-tags/{char}  → コアタグ候補
"""

from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from neme_anima.storage.project import TrainingConfig

router = APIRouter(prefix="/api/projects/{slug}/training", tags=["training"])


def _get_project(request: Request, slug: str):
    project = request.app.state.registry.get(slug)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")
    return project


class TrainingConfigPatch(BaseModel):
    """部分更新用。None フィールドは変更しない。"""
    preset: str | None = None
    diffusion_pipe_dir: str | None = None
    anima_dit_path: str | None = None
    qwen_vae_path: str | None = None
    qwen_text_encoder_path: str | None = None
    rank: int | None = None
    alpha: float | None = None
    lr: float | None = None
    epochs: int | None = None
    batch_size: int | None = None
    save_every_n_epochs: int | None = None
    keep_last_n_checkpoints: int | None = None
    trigger_token: str | None = None
    core_tag_pruning_enabled: bool | None = None
    core_tag_threshold: float | None = None
    repeat_multiplier: float | None = None
    character_slug: str | None = None  # どのキャラクターの設定か


@router.get("/config")
async def get_training_config(slug: str, request: Request) -> dict:
    project = _get_project(request, slug)
    result = {}
    for char in project.characters:
        result[char.slug] = asdict(char.training)
    return result


@router.patch("/config")
async def patch_training_config(
    slug: str, body: TrainingConfigPatch, request: Request
) -> dict:
    """指定キャラクター (省略時は最初のキャラクター) の学習設定を更新する。"""
    project = _get_project(request, slug)
    char = project._resolve_character(body.character_slug)
    cfg = char.training

    # None でないフィールドだけ上書き
    patch_data = body.model_dump(exclude={"character_slug"}, exclude_none=True)
    valid_fields = {f.name for f in fields(TrainingConfig())}
    for key, val in patch_data.items():
        if key in valid_fields:
            setattr(cfg, key, val)

    project.save()
    return asdict(cfg)


class StartTrainingRequest(BaseModel):
    character_slug: str | None = None


@router.post("/start", status_code=202)
async def start_training(
    slug: str, body: StartTrainingRequest, request: Request
) -> dict:
    """LoRA 学習をキューに積む。"""
    project = _get_project(request, slug)
    training_manager = request.app.state.training
    char = project._resolve_character(body.character_slug)

    job_id = await training_manager.start(
        project=project, character_slug=char.slug
    )
    return {"job_id": job_id}


@router.post("/stop", status_code=202)
async def stop_training(slug: str, request: Request) -> dict:
    """現在実行中の学習を停止する。"""
    training_manager = request.app.state.training
    await training_manager.stop()
    return {"ok": True}


@router.get("/status")
async def get_training_status(slug: str, request: Request) -> dict:
    """学習の現在状態を返す。"""
    training_manager = request.app.state.training
    return training_manager.status()


@router.get("/core-tags/{char_slug}")
async def get_core_tags(slug: str, char_slug: str, request: Request) -> dict:
    """コアタグ候補 (閾値以上の出現率のタグ) を返す。
    
    実際にタグ付け済みのフレームから集計する。
    """
    import json
    from collections import Counter

    project = _get_project(request, slug)
    char = project.character_by_slug(char_slug)
    if char is None:
        raise HTTPException(status_code=404, detail=f"character not found: {char_slug}")

    threshold = char.training.core_tag_threshold

    # metadata.jsonl からこのキャラクターのタグを集計
    if not project.metadata_path.exists():
        return {"core_tags": [], "threshold": threshold}

    tag_counter: Counter = Counter()
    total = 0
    with open(project.metadata_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("character_slug") != char_slug:
                continue
            total += 1
            for tag in row.get("tags", []):
                tag_counter[tag] += 1

    if total == 0:
        return {"core_tags": [], "threshold": threshold}

    core_tags = [
        {"tag": tag, "ratio": count / total}
        for tag, count in tag_counter.most_common()
        if count / total >= threshold
    ]
    return {"core_tags": core_tags, "threshold": threshold, "total_frames": total}
