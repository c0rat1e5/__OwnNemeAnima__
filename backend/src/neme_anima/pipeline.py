"""
pipeline.py — タグ付けパイプライン (シンプル版)。

■ フロー:
  ユーザーが kept/ に画像を置く (アップロード UI 経由)
      ↓
  run_tag() → WD14 タグ付け → .txt 生成 + metadata.jsonl 更新
      ↓
  dedup_all() → 重複画像を rejected/ に移動 (任意)
"""

from __future__ import annotations

import json
import logging

from neme_anima.config import Thresholds
from neme_anima.server.job_progress import JobProgress
from neme_anima.storage.project import Project

logger = logging.getLogger(__name__)


def _load_thresholds(project: Project) -> Thresholds:
    cfg_path = project.root / "thresholds.json"
    if cfg_path.exists():
        return Thresholds.from_json(cfg_path)
    return Thresholds()


def _sync_existing_txt_to_metadata(project: Project, png_files: list) -> None:
    """kept/ に .txt が存在するのに metadata.jsonl のタグが空の画像を同期する。"""
    if not project.metadata_path.exists():
        return

    rows: list[dict] = []
    with open(project.metadata_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    changed = False
    idx = {r["filename"]: i for i, r in enumerate(rows)}
    for png in png_files:
        txt = png.with_suffix(".txt")
        if not txt.is_file():
            continue
        fn = png.name
        if fn not in idx:
            continue
        if rows[idx[fn]].get("tags"):
            continue  # 既にタグあり
        tags = [t.strip() for t in txt.read_text().split(",") if t.strip()]
        rows[idx[fn]]["tags"] = tags
        changed = True

    if changed:
        with open(project.metadata_path, "w") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        logger.info("sync: updated tags from .txt files")


def run_tag(
    *,
    project: Project,
    character_slug: str | None = None,
    retag: bool = False,
    progress: JobProgress,
) -> None:
    """kept/ 内の画像に WD14 タグを付けて .txt を生成する。"""
    cfg = _load_thresholds(project)
    png_files = sorted(project.kept_dir.glob("*.png"))

    if character_slug is not None and project.metadata_path.exists():
        char_files: set[str] = set()
        with open(project.metadata_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if row.get("character_slug") == character_slug:
                        char_files.add(row["filename"])
                except json.JSONDecodeError:
                    pass
        png_files = [p for p in png_files if p.name in char_files]

    targets = [p for p in png_files if retag or not p.with_suffix(".txt").exists()]

    # .txt は存在するが metadata.jsonl のタグが空の画像を同期する
    _sync_existing_txt_to_metadata(project, png_files)

    if not targets:
        logger.info("tag: nothing to tag (all already tagged)")
        progress.update("tag", 1, 1)
        progress.done()
        return

    logger.info("tag: %d images", len(targets))
    crops = [
        {"path": str(p), "character_slug": character_slug or "default"}
        for p in targets
    ]

    from neme_anima.tag import tag_crops
    tag_crops(crops=crops, project=project, cfg=cfg.tag, progress=progress)

    from neme_anima.dedup import dedup_all
    dedup_all(project=project, cfg=cfg.dedup, progress=progress)

    logger.info("tag pipeline: done")
