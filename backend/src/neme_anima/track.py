"""
track.py — ByteTrack によるフレーム間トラッキング。

■ 役割:
  検出結果をフレーム間で繋ぎ、「同じ人物の連続した bbox 列 (トラックレット)」を作る。
  
■ ByteTrack とは？
  BYTE-Track: Multi-Object Tracking by Associating Every Detection Box (2022)
  低信頼度の検出も活用して遮蔽や一時消失に強い。
  
■ トラックレットの構造:
  {
    "track_id": 3,
    "character_slug": None,  # identify で決まる
    "frames": [
        {"frame_idx": 120, "x1": 10, "y1": 20, "x2": 80, "y2": 200, "score": 0.9},
        ...
    ]
  }
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from neme_anima.config import TrackConfig
from neme_anima.detect import DetectionMap
from neme_anima.server.job_progress import JobProgress
from neme_anima.video import Scene

logger = logging.getLogger(__name__)

Tracklet = dict[str, Any]
CACHE_FILENAME = "tracklets.parquet"


def track_detections(
    *,
    detections: DetectionMap,
    scenes: list[Scene],
    cfg: TrackConfig,
    cache_dir: Path,
    progress: JobProgress,
) -> list[Tracklet]:
    """検出結果をトラッキングしてトラックレットリストを返す。"""
    cache_path = cache_dir / CACHE_FILENAME
    if cache_path.exists():
        logger.info("track: cache hit")
        return load_tracklets_cache(cache_dir)

    progress.update("track", 0, len(scenes))

    # ByteTrack を各シーン独立で実行 (シーンをまたいで追跡しない)
    all_tracklets: list[Tracklet] = []
    global_track_offset = 0

    for scene_idx, (scene_start, scene_end) in enumerate(scenes):
        scene_tracklets = _track_scene(
            detections=detections,
            scene_start=scene_start,
            scene_end=scene_end,
            cfg=cfg,
            track_id_offset=global_track_offset,
        )
        # 最小長フィルタ
        scene_tracklets = [
            t for t in scene_tracklets
            if len(t["frames"]) >= cfg.min_tracklet_len
        ]
        all_tracklets.extend(scene_tracklets)
        if scene_tracklets:
            global_track_offset = max(t["track_id"] for t in scene_tracklets) + 1

        progress.update("track", scene_idx + 1, len(scenes))

    logger.info("track: %d tracklets", len(all_tracklets))
    _save_tracklets_cache(all_tracklets, cache_path)
    return all_tracklets


def _track_scene(
    *,
    detections: DetectionMap,
    scene_start: int,
    scene_end: int,
    cfg: TrackConfig,
    track_id_offset: int,
) -> list[Tracklet]:
    """1 シーン内をトラッキングする。

    本来は ByteTrack のバインディングを使うが、
    簡略実装として IoU ベースのグリーディマッチングを使う。
    GPU が不要なので torch なしで動く。
    """
    # アクティブなトラック: {track_id: {"frames": [...], "last_bbox": (x1,y1,x2,y2)}}
    active: dict[int, dict] = {}
    finished: list[Tracklet] = []
    next_id = track_id_offset
    lost: dict[int, dict] = {}  # 一時消失したトラック

    frame_indices = sorted(
        f for f in detections if scene_start <= f < scene_end
    )

    for frame_idx in frame_indices:
        dets = detections.get(frame_idx, [])
        if not dets:
            # フレームに検出がない場合、lost カウントを増やす
            new_lost = {}
            for tid, track in {**active, **lost}.items():
                track["lost_count"] = track.get("lost_count", 0) + 1
                if track["lost_count"] <= cfg.track_buffer:
                    new_lost[tid] = track
                else:
                    finished.append(_finalize(tid, track))
            active = {}
            lost = new_lost
            continue

        # 既存トラックと検出のマッチング (IoU)
        det_bboxes = [(d["x1"], d["y1"], d["x2"], d["y2"]) for d in dets]
        matched_dets = set()
        matched_tracks = set()
        new_active = {}

        for tid, track in {**active, **lost}.items():
            best_iou = cfg.match_thresh
            best_det_idx = -1
            for di, bbox in enumerate(det_bboxes):
                if di in matched_dets:
                    continue
                iou = _iou(track["last_bbox"], bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_det_idx = di

            if best_det_idx >= 0:
                matched_dets.add(best_det_idx)
                matched_tracks.add(tid)
                det = dets[best_det_idx]
                bbox = det_bboxes[best_det_idx]
                track["frames"].append({
                    "frame_idx": frame_idx,
                    "x1": det["x1"], "y1": det["y1"],
                    "x2": det["x2"], "y2": det["y2"],
                    "score": det["score"],
                })
                track["last_bbox"] = bbox
                track["lost_count"] = 0
                new_active[tid] = track

        # マッチしなかった既存トラックを lost に
        for tid, track in {**active, **lost}.items():
            if tid not in matched_tracks:
                track["lost_count"] = track.get("lost_count", 0) + 1
                if track["lost_count"] <= cfg.track_buffer:
                    lost[tid] = track
                else:
                    finished.append(_finalize(tid, track))

        # 未マッチの検出 → 新しいトラック
        for di, det in enumerate(dets):
            if di not in matched_dets and det["score"] >= cfg.track_thresh:
                tid = next_id
                next_id += 1
                new_active[tid] = {
                    "frames": [{
                        "frame_idx": frame_idx,
                        "x1": det["x1"], "y1": det["y1"],
                        "x2": det["x2"], "y2": det["y2"],
                        "score": det["score"],
                    }],
                    "last_bbox": (det["x1"], det["y1"], det["x2"], det["y2"]),
                    "lost_count": 0,
                }

        active = new_active
        # lost は次フレームで再チェックするが active とは別管理
        lost = {tid: t for tid, t in lost.items() if tid not in matched_tracks}

    # 残ったトラックをフィナライズ
    for tid, track in {**active, **lost}.items():
        finished.append(_finalize(tid, track))

    return finished


def _finalize(track_id: int, track: dict) -> Tracklet:
    return {
        "track_id": track_id,
        "character_slug": None,
        "frames": track["frames"],
    }


def _iou(a: tuple, b: tuple) -> float:
    """2 つのバウンディングボックスの IoU を計算する。"""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


def _save_tracklets_cache(tracklets: list[Tracklet], path: Path) -> None:
    """トラックレットを Parquet でキャッシュする。"""
    import json
    import pandas as pd

    rows = [
        {
            "track_id": t["track_id"],
            "frames_json": json.dumps(t["frames"]),
        }
        for t in tracklets
    ]
    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["track_id", "frames_json"]
    )
    df.to_parquet(path, index=False)


def load_tracklets_cache(cache_dir: Path) -> list[Tracklet]:
    """キャッシュからトラックレットを読み込む。"""
    import json
    import pandas as pd

    path = cache_dir / CACHE_FILENAME
    if not path.exists():
        return []
    df = pd.read_parquet(path)
    return [
        {
            "track_id": int(row["track_id"]),
            "character_slug": None,
            "frames": json.loads(row["frames_json"]),
        }
        for _, row in df.iterrows()
    ]
