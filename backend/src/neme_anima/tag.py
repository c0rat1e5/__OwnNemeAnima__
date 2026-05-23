"""
tag.py — WD14 EVA02-Large v3 による Danbooru タグ付け。

■ 役割:
  クロップ画像ごとに WD14 タグ付けを行い、kohya-ss 形式の .txt を生成する。
  .txt の内容は "tag1, tag2, tag3, ..." という CSV 形式。
  また metadata.jsonl に各フレームのメタデータを追記する。

■ WD14 とは？
  WD (Waifu Diffusion) 14 タガー。Danbooru のタグを予測するモデル。
  EVA02-Large v3 (SmilingWolf/wd-eva02-large-tagger-v3) が現在最高精度。
  imgutils 経由で簡単に使える。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from neme_anima.config import TagConfig
from neme_anima.crop import CroppedFrame
from neme_anima.server.job_progress import JobProgress
from neme_anima.storage.project import Project

logger = logging.getLogger(__name__)


def tag_crops(
    *,
    crops: list[CroppedFrame],
    project: Project,
    cfg: TagConfig,
    progress: JobProgress,
) -> None:
    """全クロップ画像に WD14 タグを付けて .txt と metadata.jsonl を生成する。"""
    if not crops:
        return

    progress.update("tag", 0, len(crops))

    # imgutils の WD14 タガーを遅延 import
    from imgutils.tagging import get_wd14_tags
    import torch

    metadata_rows: list[dict[str, Any]] = []

    for ci, crop in enumerate(crops):
        path = Path(crop["path"])
        if not path.is_file():
            continue

        from PIL import Image
        img = Image.open(path).convert("RGB")

        try:
            # WD14 でタグを予測
            # 戻り値: (rating_dict, character_dict, general_dict)
            rating, chars, general = get_wd14_tags(
                img,
                model_name=cfg.model_name,
                general_threshold=cfg.general_threshold,
                character_threshold=cfg.character_threshold,
            )
        except Exception as exc:
            logger.warning("tag failed: %s: %s", path.name, exc)
            continue

        # タグを結合してリストにする
        tags: list[str] = list(general.keys()) + list(chars.keys())

        # アンダースコアをスペースに変換
        if cfg.no_underline:
            tags = [t.replace("_", " ") for t in tags]

        # 除外タグをフィルタ
        if cfg.exclude_tags:
            excl = set(cfg.exclude_tags)
            tags = [t for t in tags if t not in excl]

        # .txt ファイルを書き出す (kohya-ss 形式)
        txt_path = path.with_suffix(".txt")
        txt_path.write_text(", ".join(tags))

        metadata_rows.append({
            "filename": path.name,
            "character_slug": crop["character_slug"],
            "track_id": crop["track_id"],
            "frame_idx": crop["frame_idx"],
            "source_idx": crop["source_idx"],
            "video_stem": crop["video_stem"],
            "tags": tags,
            "rating": max(rating, key=rating.get) if rating else "general",
        })

        # VRAM フラッシュ
        if (ci + 1) % cfg.vram_flush_every == 0 and torch.cuda.is_available():
            torch.cuda.empty_cache()

        progress.update("tag", ci + 1, len(crops))

    # metadata.jsonl に追記
    if metadata_rows:
        with open(project.metadata_path, "a") as f:
            for row in metadata_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    logger.info("tag: %d images tagged", len(metadata_rows))
