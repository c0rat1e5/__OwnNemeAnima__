"""
video.py — PySceneDetect によるシーン分割。

■ 役割:
  動画をショット(シーン)のリストに分割する。
  各シーンは (start_frame, end_frame) のタプル。
  
■ なぜシーン分割が必要？
  ByteTrack はシーン内でトラックレットを繋ぐ。
  シーン切り替えをまたいで同じ ID を使うと誤追跡になる。
"""

from __future__ import annotations

import logging
from pathlib import Path

from neme_anima.config import SceneConfig
from neme_anima.storage.project import Segment

logger = logging.getLogger(__name__)

# シーン = (開始フレーム番号, 終了フレーム番号) のタプル
Scene = tuple[int, int]


def detect_scenes(
    video_path: Path,
    *,
    cfg: SceneConfig,
    segments: list[Segment] | None = None,
) -> list[Scene]:
    """動画をシーンのリストに分割して返す。

    Args:
        video_path: 入力動画のパス
        cfg:        SceneConfig (閾値・最小シーン長)
        segments:   処理対象の時間範囲 (空リスト = 全体)
    
    Returns:
        [(start_frame, end_frame), ...] のリスト (0-indexed)
    """
    # PySceneDetect のインポートは実行時まで遅延
    from scenedetect import detect, ContentDetector, SceneManager
    from scenedetect.video_splitter import split_video_ffmpeg
    import cv2

    logger.info("scene detection: %s threshold=%.1f", video_path.name, cfg.threshold)

    # scenedetect を使ってシーンを検出
    scenes_raw = detect(
        str(video_path),
        ContentDetector(threshold=cfg.threshold, min_scene_len=cfg.min_scene_len_frames),
    )

    # (FrameTimecode, FrameTimecode) → (int, int) に変換
    all_scenes: list[Scene] = [
        (s[0].get_frames(), s[1].get_frames())
        for s in scenes_raw
    ]

    # セグメント (時間範囲) によるフィルタリング
    if segments:
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()

        filtered: list[Scene] = []
        for seg in segments:
            start_f = int(seg.start_seconds * fps)
            end_f = int(seg.end_seconds * fps)
            for scene_start, scene_end in all_scenes:
                # シーンとセグメントが重なっているか
                if scene_end >= start_f and scene_start <= end_f:
                    # セグメント範囲にクリップ
                    filtered.append((
                        max(scene_start, start_f),
                        min(scene_end, end_f),
                    ))
        all_scenes = filtered

    logger.info("scenes: %d total", len(all_scenes))
    return all_scenes
