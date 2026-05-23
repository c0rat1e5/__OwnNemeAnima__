"""
detect.py — DeepGHS YOLO によるキャラクター検出。

■ 役割:
  各フレームをアニメキャラクター用の YOLOv8 に通し、
  人物バウンディングボックスを取得する。
  
■ キャッシュ:
  検出結果は Parquet 形式でキャッシュする。
  閾値を変えたい場合は detect 段階からやり直すが、
  rerun (identify からのやり直し) の場合はこのキャッシュを使う。
  
■ imgutils とは？
  DeepGHS がメンテする huggingface-based アニメ画像処理ライブラリ。
  アニメ専用 YOLOv8 の人物・顔検出モデルが含まれる。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from neme_anima.config import DetectConfig
from neme_anima.server.job_progress import JobProgress
from neme_anima.video import Scene

logger = logging.getLogger(__name__)

# 1 フレームの検出結果の型
Detection = dict[str, Any]
# {frame_idx: [Detection, ...]}
DetectionMap = dict[int, list[Detection]]

CACHE_FILENAME = "detections.parquet"


def detect_characters(
    *,
    video_path: Path,
    scenes: list[Scene],
    cfg: DetectConfig,
    cache_dir: Path,
    progress: JobProgress,
) -> DetectionMap:
    """全シーンのフレームを検出し、フレーム番号 → 検出リストの辞書を返す。
    
    キャッシュが存在する場合はそちらを返す。
    """
    cache_path = cache_dir / CACHE_FILENAME
    if cache_path.exists():
        logger.info("detect: cache hit, loading %s", cache_path)
        return _load_cache(cache_path)

    # 総フレーム数を計算 (進捗表示用)
    total_frames = sum(
        (e - s) // cfg.frame_stride for s, e in scenes
    )
    progress.update("detect", 0, max(total_frames, 1))

    # imgutils の遅延 import (GPU 重い)
    from imgutils.detect import detect_person

    import cv2
    cap = cv2.VideoCapture(str(video_path))
    detection_map: DetectionMap = {}
    processed = 0

    try:
        for scene_start, scene_end in scenes:
            for frame_idx in range(scene_start, scene_end, cfg.frame_stride):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame_bgr = cap.read()
                if not ret:
                    break

                # BGR → RGB (imgutils は RGB を期待)
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                from PIL import Image
                pil_img = Image.fromarray(frame_rgb)

                # 人物検出
                persons = detect_person(
                    pil_img,
                    conf=cfg.person_score_min,
                )
                if persons:
                    detection_map[frame_idx] = [
                        {
                            "frame_idx": frame_idx,
                            "x1": int(bbox[0]),
                            "y1": int(bbox[1]),
                            "x2": int(bbox[2]),
                            "y2": int(bbox[3]),
                            "score": float(score),
                            "label": label,
                        }
                        for (bbox, score, label) in persons
                        if score >= cfg.person_score_min
                    ]

                processed += 1
                if processed % 50 == 0:
                    progress.update("detect", processed, total_frames)
    finally:
        cap.release()

    progress.update("detect", total_frames, total_frames)
    logger.info("detect: %d frames with detections", len(detection_map))

    # キャッシュに保存
    _save_cache(detection_map, cache_path)
    return detection_map


def _save_cache(detection_map: DetectionMap, path: Path) -> None:
    """検出結果を Parquet で保存する。"""
    import pandas as pd

    rows = []
    for frame_idx, dets in detection_map.items():
        for d in dets:
            rows.append(d)

    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["frame_idx", "x1", "y1", "x2", "y2", "score", "label"]
    )
    df.to_parquet(path, index=False)
    logger.debug("detect cache saved: %d rows", len(df))


def _load_cache(path: Path) -> DetectionMap:
    """Parquet から検出結果を読み込む。"""
    import pandas as pd

    df = pd.read_parquet(path)
    detection_map: DetectionMap = {}
    for _, row in df.iterrows():
        frame_idx = int(row["frame_idx"])
        if frame_idx not in detection_map:
            detection_map[frame_idx] = []
        detection_map[frame_idx].append(row.to_dict())
    return detection_map
