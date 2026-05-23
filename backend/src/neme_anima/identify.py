"""
identify.py — CCIP によるキャラクター識別。

■ CCIP とは？
  Character Consistency Identification Perceptual model。
  DeepGHS が学習した「アニメキャラクターの一致度を測る埋め込みモデル」。
  2 つの画像パッチを埋め込み、L2 距離で「同じキャラかどうか」を判定する。
  距離が小さいほど同じキャラクターに近い (0.0 = 完全一致)。

■ フロー:
  1. 各トラックレットから代表フレームをサンプリング
  2. フレームパッチを CCIP に通して埋め込みを得る
  3. プロジェクトの参照画像の埋め込みと L2 距離を計算
  4. 距離が閾値以下のキャラクターに割り当てる
  5. 閾値を超えたトラックレットは「識別不可」として捨てる
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from neme_anima.config import IdentifyConfig
from neme_anima.server.job_progress import JobProgress
from neme_anima.storage.project import Project
from neme_anima.track import Tracklet

logger = logging.getLogger(__name__)

IdentifiedTracklet = dict[str, Any]


def identify_tracklets(
    *,
    video_path: Path,
    tracklets: list[Tracklet],
    project: Project,
    source_idx: int,
    cfg: IdentifyConfig,
    progress: JobProgress,
) -> list[IdentifiedTracklet]:
    """各トラックレットをキャラクターに割り当てる。

    Returns:
        character_slug が設定されたトラックレットのリスト。
        どのキャラクターにも一致しなかったものは除外される。
    """
    if not tracklets:
        return []

    progress.update("identify", 0, len(tracklets))

    # imgutils の CCIP を遅延 import
    from imgutils.metrics import ccip_extract_feature, ccip_batch_same

    # ── 参照画像の埋め込みを計算 ──────────────────────────────
    ref_embeddings: dict[str, list[np.ndarray]] = {}  # {char_slug: [emb, ...]}
    for char in project.characters:
        eff_refs = project.effective_refs_for(source_idx, character_slug=char.slug)
        if not eff_refs:
            continue
        embs = []
        for ref_path in eff_refs:
            p = Path(ref_path)
            if p.is_file():
                try:
                    from PIL import Image
                    img = Image.open(p).convert("RGB")
                    emb = ccip_extract_feature(img)
                    embs.append(emb)
                except Exception as exc:
                    logger.warning("ref embed failed: %s: %s", p.name, exc)
        if embs:
            ref_embeddings[char.slug] = embs

    if not ref_embeddings:
        logger.warning("identify: no reference embeddings available")
        return []

    # ── ビデオキャプチャ ───────────────────────────────────────
    import cv2
    cap = cv2.VideoCapture(str(video_path))

    identified: list[IdentifiedTracklet] = []

    for ti, tracklet in enumerate(tracklets):
        # トラックレットから代表フレームをサンプリング
        frames = tracklet["frames"]
        step = max(1, len(frames) // cfg.sample_frames_per_tracklet)
        sample_frames = frames[::step][: cfg.sample_frames_per_tracklet]

        # 各サンプルフレームの bbox パッチを取得して埋め込む
        track_embs = []
        for frame_info in sample_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_info["frame_idx"])
            ret, bgr = cap.read()
            if not ret:
                continue
            # bbox をクロップ
            x1, y1, x2, y2 = (
                frame_info["x1"], frame_info["y1"],
                frame_info["x2"], frame_info["y2"],
            )
            patch_bgr = bgr[max(0, y1):y2, max(0, x1):x2]
            if patch_bgr.size == 0:
                continue
            from PIL import Image
            patch_rgb = Image.fromarray(cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2RGB))
            try:
                emb = ccip_extract_feature(patch_rgb)
                track_embs.append(emb)
            except Exception:
                pass

        if not track_embs:
            continue

        # ── 各キャラクターとの距離を計算 ─────────────────────
        best_slug: str | None = None
        best_dist: float = float("inf")

        track_emb_mean = np.mean(track_embs, axis=0)

        for char_slug, ref_embs in ref_embeddings.items():
            ref_emb_mean = np.mean(ref_embs, axis=0)
            dist = float(np.linalg.norm(track_emb_mean - ref_emb_mean))
            if dist < best_dist:
                best_dist = dist
                best_slug = char_slug

        # 閾値チェック
        if best_slug is not None and best_dist <= cfg.body_max_distance_loose:
            identified_tracklet = dict(tracklet)
            identified_tracklet["character_slug"] = best_slug
            identified_tracklet["ccip_distance"] = best_dist
            identified.append(identified_tracklet)

        progress.update("identify", ti + 1, len(tracklets))

    cap.release()
    logger.info(
        "identify: %d/%d tracklets identified",
        len(identified), len(tracklets),
    )
    return identified
