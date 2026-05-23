"""
pipeline.py — 抽出パイプラインのオーケストレーター。

■ 全体フロー:
  run_extract():
    ① video.py      → PySceneDetect でシーン分割
    ② detect.py     → YOLO でキャラクター検出 (キャッシュ有)
    ③ track.py      → ByteTrack でトラッキング (キャッシュ有)
    ④ identify.py   → CCIP でキャラクター識別
    ⑤ frame_select  → シャープネス等でフレーム選択
    ⑥ crop.py       → 背景付きクロップ (長辺 1024px)
    ⑦ tag.py        → WD14 タグ付け + .txt 生成
    ⑧ dedup.py      → CCIP による重複除去

  run_rerun():
    ①②③ をスキップして ④ から再実行 (閾値だけ変えたい場合)

■ GPU の重い import はここで行う。
  サーバー起動時ではなく、最初のジョブ実行時に初めてロードされる。
  これにより UI は GPU 準備前でも表示できる。
"""

from __future__ import annotations

import logging
from pathlib import Path

from neme_anima.config import Thresholds
from neme_anima.server.job_progress import JobProgress
from neme_anima.storage.project import Project

logger = logging.getLogger(__name__)


def _load_thresholds(project: Project) -> Thresholds:
    """プロジェクト固有の thresholds.json があれば読み込む。なければデフォルト。"""
    cfg_path = project.root / "thresholds.json"
    if cfg_path.exists():
        return Thresholds.from_json(cfg_path)
    return Thresholds()


def run_extract(
    *,
    project: Project,
    source_idx: int,
    progress: JobProgress,
) -> None:
    """フルパイプラインを実行する (GPU 必須)。

    Args:
        project:    対象プロジェクト
        source_idx: project.sources 内のインデックス
        progress:   SSE 進捗通知オブジェクト
    """
    cfg = _load_thresholds(project)
    source = project.sources[source_idx]
    video_path = Path(source.path)

    logger.info("extract.start project=%s video=%s", project.slug, video_path.name)

    # ── ① シーン分割 ───────────────────────────────────────────
    progress.update("scenes", 0, 1)
    from neme_anima.video import detect_scenes
    scenes = detect_scenes(
        video_path,
        cfg=cfg.scene,
        segments=source.segments,
    )
    progress.update("scenes", 1, 1)
    logger.info("scenes detected: %d", len(scenes))

    # ── ② 検出 (キャッシュ) ────────────────────────────────────
    cache_dir = project.cache_dir_for(project.video_stem(source_idx))
    cache_dir.mkdir(parents=True, exist_ok=True)

    from neme_anima.detect import detect_characters
    detections = detect_characters(
        video_path=video_path,
        scenes=scenes,
        cfg=cfg.detect,
        cache_dir=cache_dir,
        progress=progress,
    )

    # ── ③ トラッキング (キャッシュ) ────────────────────────────
    from neme_anima.track import track_detections
    tracklets = track_detections(
        detections=detections,
        scenes=scenes,
        cfg=cfg.track,
        cache_dir=cache_dir,
        progress=progress,
    )

    # ── ④⑤⑥⑦⑧ 識別以降 ─────────────────────────────────────
    _run_from_identify(
        project=project,
        source_idx=source_idx,
        video_path=video_path,
        tracklets=tracklets,
        cfg=cfg,
        progress=progress,
    )

    logger.info("extract.done project=%s video=%s", project.slug, video_path.name)


def run_rerun(
    *,
    project: Project,
    source_idx: int,
    progress: JobProgress,
    video: str | None = None,
) -> None:
    """キャッシュを使って ④ 識別から再実行する。

    Args:
        video: ビデオ stem で絞り込む場合に指定 (None = source_idx で決定)。
    """
    cfg = _load_thresholds(project)
    source = project.sources[source_idx]
    video_path = Path(source.path)
    cache_dir = project.cache_dir_for(project.video_stem(source_idx))

    from neme_anima.track import load_tracklets_cache
    tracklets = load_tracklets_cache(cache_dir)

    if not tracklets:
        logger.warning("rerun: no cached tracklets for %s", video_path.name)
        return

    _run_from_identify(
        project=project,
        source_idx=source_idx,
        video_path=video_path,
        tracklets=tracklets,
        cfg=cfg,
        progress=progress,
    )


def _run_from_identify(
    *,
    project: Project,
    source_idx: int,
    video_path: Path,
    tracklets: list,
    cfg: Thresholds,
    progress: JobProgress,
) -> None:
    """識別ステージ以降を実行する共通処理。"""

    # ── ④ キャラクター識別 ────────────────────────────────────
    from neme_anima.identify import identify_tracklets
    identified = identify_tracklets(
        video_path=video_path,
        tracklets=tracklets,
        project=project,
        source_idx=source_idx,
        cfg=cfg.identify,
        progress=progress,
    )

    # ── ⑤ フレーム選択 ───────────────────────────────────────
    from neme_anima.frame_select import select_frames
    selected = select_frames(
        video_path=video_path,
        identified=identified,
        cfg=cfg.frame_select,
        progress=progress,
    )

    # ── ⑥ クロップ ───────────────────────────────────────────
    from neme_anima.crop import crop_frames
    cropped = crop_frames(
        video_path=video_path,
        selected=selected,
        project=project,
        source_idx=source_idx,
        cfg=cfg.crop,
        progress=progress,
    )

    # ── ⑦ タグ付け ───────────────────────────────────────────
    from neme_anima.tag import tag_crops
    tag_crops(
        crops=cropped,
        project=project,
        cfg=cfg.tag,
        progress=progress,
    )

    # ── ⑧ 重複除去 ───────────────────────────────────────────
    from neme_anima.dedup import dedup_crops
    dedup_crops(
        project=project,
        source_idx=source_idx,
        cfg=cfg.dedup,
        progress=progress,
    )
