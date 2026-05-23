"""
dedup.py — CCIP 埋め込みによる知覚的重複除去。

■ 役割:
  kept/ フォルダ内で「ほぼ同じポーズ・構図」のクロップを検出して rejected/ に移す。
  
  タグが同じでも微妙に違うフレームが学習データに入ると、
  LoRA が特定のポーズに過学習する。dedup でそれを防ぐ。

■ アルゴリズム:
  1. 全クロップを CCIP に通して埋め込みを取得
  2. 埋め込み間の L2 距離行列を計算
  3. 距離が max_distance 以下のペアを「重複」と判定
  4. グリーディに「代表」を 1 つ残して残りを rejected/ に移動
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from neme_anima.config import DedupConfig
from neme_anima.server.job_progress import JobProgress
from neme_anima.storage.project import Project

logger = logging.getLogger(__name__)


def dedup_crops(
    *,
    project: Project,
    source_idx: int,
    cfg: DedupConfig,
    progress: JobProgress,
) -> None:
    """このソースの kept クロップ間の重複を除去する。"""
    video_stem = project.video_stem(source_idx)
    kept_dir = project.kept_dir

    # このソースのクロップだけを対象にする
    png_files = sorted(
        p for p in kept_dir.glob(f"{video_stem}__*.png")
        if p.is_file()
    )

    if len(png_files) < 2:
        progress.update("dedup", 1, 1)
        return

    progress.update("dedup", 0, len(png_files))

    # CCIP で全画像を埋め込む
    from imgutils.metrics import ccip_extract_feature
    from PIL import Image
    import numpy as np

    embeddings: list[np.ndarray] = []
    valid_files: list[Path] = []

    for i, png in enumerate(png_files):
        try:
            img = Image.open(png).convert("RGB")
            emb = ccip_extract_feature(img)
            embeddings.append(emb)
            valid_files.append(png)
        except Exception as exc:
            logger.warning("dedup: embed failed %s: %s", png.name, exc)

        if (i + 1) % cfg.embed_batch_size == 0:
            progress.update("dedup", i + 1, len(png_files))

    if not embeddings:
        return

    emb_matrix = np.stack(embeddings)  # (N, D)

    # L2 距離行列を計算
    # dist[i][j] = ||emb[i] - emb[j]||
    diff = emb_matrix[:, np.newaxis, :] - emb_matrix[np.newaxis, :, :]
    dist_matrix = np.linalg.norm(diff, axis=-1)

    # グリーディ重複除去
    n = len(valid_files)
    kept = [True] * n  # True = keep

    for i in range(n):
        if not kept[i]:
            continue
        for j in range(i + 1, n):
            if not kept[j]:
                continue
            if dist_matrix[i][j] <= cfg.max_distance:
                # j を捨てる (i を代表として残す)
                kept[j] = False

    # 重複ファイルを rejected に移動
    removed = 0
    for i, (png, keep) in enumerate(zip(valid_files, kept)):
        if not keep:
            dst = project.rejected_dir / png.name
            shutil.move(str(png), str(dst))
            # .txt も移動
            txt = png.with_suffix(".txt")
            if txt.is_file():
                shutil.move(str(txt), str(project.rejected_dir / txt.name))
            removed += 1

    # metadata.jsonl から除去されたファイルを削除
    if removed > 0 and project.metadata_path.exists():
        removed_names = {
            p.name for p, keep in zip(valid_files, kept) if not keep
        }
        rows = []
        with open(project.metadata_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if row.get("filename") not in removed_names:
                        rows.append(row)
                except json.JSONDecodeError:
                    pass
        with open(project.metadata_path, "w") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    progress.update("dedup", len(png_files), len(png_files))
    logger.info(
        "dedup: %d/%d images removed as duplicates",
        removed, len(valid_files),
    )
