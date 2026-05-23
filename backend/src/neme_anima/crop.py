"""
crop.py — キャラクタークロップ画像の生成。

■ 役割:
  選択されたフレームの bbox を使って、キャラクターをクロップする。
  長辺 1024px にリサイズし、背景ごと保存する。
  出力ファイル名: {video_stem}__{scene}_{track}_{frame}.png

■ ファイル名の例:
  ep01__s003_t012_f000847.png
  → ep01: ビデオ名
  → s003: シーン番号
  → t012: トラックID
  → f000847: フレーム番号
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from neme_anima.config import CropConfig
from neme_anima.frame_select import SelectedFrame
from neme_anima.server.job_progress import JobProgress
from neme_anima.storage.project import Project

logger = logging.getLogger(__name__)

CroppedFrame = dict[str, Any]


def crop_frames(
    *,
    video_path: Path,
    selected: list[SelectedFrame],
    project: Project,
    source_idx: int,
    cfg: CropConfig,
    progress: JobProgress,
) -> list[CroppedFrame]:
    """選択フレームをクロップして kept/ に保存する。"""
    import cv2
    from PIL import Image

    cap = cv2.VideoCapture(str(video_path))
    video_stem = project.video_stem(source_idx)
    kept_dir = project.kept_dir

    cropped: list[CroppedFrame] = []
    progress.update("crop", 0, len(selected))

    for ci, sf in enumerate(selected):
        cap.set(cv2.CAP_PROP_POS_FRAMES, sf["frame_idx"])
        ret, bgr = cap.read()
        if not ret:
            continue

        h, w = bgr.shape[:2]
        x1, y1, x2, y2 = sf["x1"], sf["y1"], sf["x2"], sf["y2"]

        # パディングを加えてクロップ
        bw = x2 - x1
        bh = y2 - y1
        pad_x = int(bw * cfg.pad_ratio)
        pad_y = int(bh * cfg.pad_ratio)
        cx1 = max(0, x1 - pad_x)
        cy1 = max(0, y1 - pad_y)
        cx2 = min(w, x2 + pad_x)
        cy2 = min(h, y2 + pad_y)

        crop_bgr = bgr[cy1:cy2, cx1:cx2]
        if crop_bgr.size == 0:
            continue

        # 長辺 longest_side px にリサイズ
        ch, cw = crop_bgr.shape[:2]
        scale = cfg.longest_side / max(ch, cw)
        new_w = int(cw * scale)
        new_h = int(ch * scale)
        resized = cv2.resize(crop_bgr, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        # ファイル名生成: {video_stem}__t{track_id:04d}_f{frame_idx:07d}.png
        filename = (
            f"{video_stem}__t{sf['track_id']:04d}_f{sf['frame_idx']:07d}.png"
        )
        out_path = kept_dir / filename
        Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)).save(out_path)

        cropped.append({
            "filename": filename,
            "path": str(out_path),
            "track_id": sf["track_id"],
            "character_slug": sf["character_slug"],
            "frame_idx": sf["frame_idx"],
            "source_idx": source_idx,
            "video_stem": video_stem,
        })

        progress.update("crop", ci + 1, len(selected))

    cap.release()
    logger.info("crop: %d images saved to %s", len(cropped), kept_dir)
    return cropped
