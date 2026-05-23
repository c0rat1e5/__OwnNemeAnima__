"""
frame_select.py — シャープネス・視認性・アスペクト比でフレームを選ぶ。

■ 役割:
  識別済みのトラックレットから「最も学習に適したフレーム」を選ぶ。
  - 短いトラックレット → top_k_short 枚
  - 長いトラックレット → top_k_long 枚

■ 品質スコアの計算:
  score = シャープネス × 視認率 × アスペクト比ペナルティ
  
  シャープネス: Laplacian 分散 (高いほどシャープ)
  視認率:      bbox が画面に収まっている割合
  アスペクト比: 人物として自然な縦長度合い (極端に正方形だと減点)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from neme_anima.config import FrameSelectConfig
from neme_anima.server.job_progress import JobProgress
from neme_anima.track import Tracklet

logger = logging.getLogger(__name__)

SelectedFrame = dict[str, Any]


def select_frames(
    *,
    video_path: Path,
    identified: list[Tracklet],
    cfg: FrameSelectConfig,
    progress: JobProgress,
) -> list[SelectedFrame]:
    """各トラックレットから最良フレームを選んで返す。"""
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    cap.release()

    selected: list[SelectedFrame] = []
    progress.update("select", 0, len(identified))

    for ti, tracklet in enumerate(identified):
        frames = tracklet["frames"]
        duration_s = (frames[-1]["frame_idx"] - frames[0]["frame_idx"]) / fps

        # トラックレットの長さで top_k を決める
        if duration_s < cfg.short_tracklet_seconds:
            top_k = cfg.top_k_short
        else:
            top_k = cfg.top_k_long

        # 候補フレームを等間隔にサンプリング
        total = len(frames)
        if total <= cfg.candidate_cap:
            candidates = frames
        else:
            step = total // cfg.candidate_cap
            candidates = frames[::step][: cfg.candidate_cap]

        # 各候補のスコアを計算
        scored = _score_candidates(candidates, video_path, width, height)
        scored.sort(key=lambda x: x["score"], reverse=True)

        # top_k 枚を、最低フレーム間隔を保ちながら選ぶ
        picks: list[dict] = []
        for s in scored:
            if len(picks) >= top_k:
                break
            fi = s["frame_idx"]
            # 既存の pick と最低間隔を確保
            if all(abs(fi - p["frame_idx"]) >= cfg.dedup_min_frame_gap for p in picks):
                picks.append(s)

        for pick in picks:
            selected.append({
                "track_id": tracklet["track_id"],
                "character_slug": tracklet["character_slug"],
                "frame_idx": pick["frame_idx"],
                "x1": pick["x1"],
                "y1": pick["y1"],
                "x2": pick["x2"],
                "y2": pick["y2"],
                "score": pick["score"],
            })

        progress.update("select", ti + 1, len(identified))

    logger.info("select: %d frames selected from %d tracklets", len(selected), len(identified))
    return selected


def _score_candidates(
    frames: list[dict], video_path: Path, frame_w: float, frame_h: float
) -> list[dict]:
    """候補フレームをビデオから読んでスコアを付ける。"""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video_path))
    scored = []

    for f in frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f["frame_idx"])
        ret, bgr = cap.read()
        if not ret:
            continue

        x1, y1, x2, y2 = f["x1"], f["y1"], f["x2"], f["y2"]
        patch = bgr[max(0, y1):y2, max(0, x1):x2]
        if patch.size == 0:
            continue

        # シャープネス (Laplacian の分散)
        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        # 視認率 (bbox が画面内に収まっている割合)
        clipped_w = min(x2, frame_w) - max(x1, 0)
        clipped_h = min(y2, frame_h) - max(y1, 0)
        bbox_w = x2 - x1
        bbox_h = y2 - y1
        visibility = (clipped_w * clipped_h) / max(bbox_w * bbox_h, 1)

        # アスペクト比ペナルティ (縦長すぎ/横長すぎは減点)
        ar = bbox_h / max(bbox_w, 1)
        ar_score = 1.0 if 1.2 <= ar <= 3.0 else 0.5

        score = sharpness * visibility * ar_score
        scored.append({**f, "score": score})

    cap.release()
    return scored
