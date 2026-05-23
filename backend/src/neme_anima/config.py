"""
config.py — パイプライン全体で使う閾値・設定値の定義。

各ステージ (シーン分割 → 検出 → トラッキング → 識別 → フレーム選択
            → クロップ → タグ付け → 重複除去) に対応するデータクラスを持つ。
project.json に保存・読み込みできる。

■ なぜデータクラス？
  - フィールド名が型と一緒に一覧できる
  - asdict() で dict → JSON に変換できる
  - デフォルト値が明示されているので「何も設定しなくても動く」
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def _filter_known(dc_cls: type, raw: dict) -> dict:
    """知らないキーを無視して dataclass に渡せる dict を返す。
    
    古い project.json に存在したキーが削除されていても
    クラッシュしないようにするためのヘルパー。
    """
    declared = {f.name for f in fields(dc_cls)}
    return {k: v for k, v in raw.items() if k in declared}


# ─────────────────────────────────────────────
# ① シーン分割 (PySceneDetect)
# ─────────────────────────────────────────────
@dataclass
class SceneConfig:
    """動画をショット(シーン)に分割するときの設定。
    
    threshold: フレーム間の輝度差がこの値を超えたらシーン切り替えと判定。
               高いほど「大きな変化でしか切らない」→ シーンが長くなる。
    min_scene_len_frames: この未満のシーンは無視する (短すぎるカットを弾く)。
    """
    threshold: float = 27.0
    min_scene_len_frames: int = 8


# ─────────────────────────────────────────────
# ② キャラクター検出 (DeepGHS YOLO via imgutils)
# ─────────────────────────────────────────────
@dataclass
class DetectConfig:
    """YOLOv8 アニメ人物検出の設定。
    
    person_score_min: 人物バウンディングボックスの信頼スコア下限。
    face_score_min:   顔 bbox の信頼スコア下限。
    frame_stride:     N フレームに 1 回だけ検出する (速度 vs 精度のトレードオフ)。
    detect_faces:     顔ストリームも使うか (False にすると検出が ~45% 速くなる)。
    """
    person_score_min: float = 0.35
    face_score_min: float = 0.35
    frame_stride: int = 4
    detect_faces: bool = False


# ─────────────────────────────────────────────
# ③ トラッキング (ByteTrack)
# ─────────────────────────────────────────────
@dataclass
class TrackConfig:
    """ByteTrack によるフレーム間トラックレット連結の設定。
    
    track_thresh:     検出スコアがこれ以上のものを「高信頼」として扱う。
    match_thresh:     IoU マッチングの閾値。
    track_buffer:     何フレーム消えたらトラックを閉じるか。
    min_tracklet_len: これ未満のトラックレットは捨てる。
    """
    track_thresh: float = 0.25
    match_thresh: float = 0.8
    frame_rate: int = 30
    track_buffer: int = 30
    min_tracklet_len: int = 3


# ─────────────────────────────────────────────
# ④ キャラクター識別 (CCIP)
# ─────────────────────────────────────────────
@dataclass
class IdentifyConfig:
    """CCIP (Character Consistency Identification Perceptual) の距離閾値。
    
    距離が小さいほど「同じキャラクター」に近い。
    body_max_distance_strict: これ以下 → 高確信度で keep
    body_max_distance_loose:  これ以下 → 中確信度で keep
    sample_frames_per_tracklet: トラックレットから何フレームを識別に使うか。
    """
    body_max_distance_strict: float = 0.15
    body_max_distance_loose: float = 0.20
    sample_frames_per_tracklet: int = 5


# ─────────────────────────────────────────────
# ⑤ フレーム選択 (シャープネス・視認性・アスペクト比)
# ─────────────────────────────────────────────
@dataclass
class FrameSelectConfig:
    """トラックレットから「最良フレーム」を選ぶときの設定。
    
    短いトラックレット (< short_tracklet_seconds) → top_k_short 枚
    長いトラックレット (>= long_tracklet_seconds)  → top_k_long 枚
    """
    short_tracklet_seconds: float = 1.0
    long_tracklet_seconds: float = 5.0
    top_k_short: int = 1
    top_k_long: int = 3
    candidate_cap: int = 20      # 長いトラックレットでは最大この数の候補を評価
    dedup_min_frame_gap: int = 4 # 選んだフレーム同士は最低この間隔を空ける


# ─────────────────────────────────────────────
# ⑥ クロップ (背景付きで長辺 1024px)
# ─────────────────────────────────────────────
@dataclass
class CropConfig:
    """キャラクタークロップの設定。
    
    longest_side: 出力画像の長辺ピクセル数。
    pad_ratio:    バウンディングボックスの周囲に追加するパディング (bbox サイズの比率)。
    """
    longest_side: int = 1024
    pad_ratio: float = 0.10


# ─────────────────────────────────────────────
# ⑦ タグ付け (WD14 EVA02-Large v3)
# ─────────────────────────────────────────────
@dataclass
class TagConfig:
    """WD14 Danbooru タグ付けの設定。
    
    model_name:          imgutils で使うモデル名。
    general_threshold:   一般タグの信頼スコア閾値。
    character_threshold: キャラクタータグの信頼スコア閾値。
    no_underline:        True → アンダースコアをスペースに変換 (例: long_hair → long hair)。
    drop_overlap:        True → 上位概念と重複するタグを削除。
    exclude_tags:        常に除外するタグのリスト。
    vram_flush_every:    N 枚ごとに torch.cuda.empty_cache() を呼ぶ。
    """
    model_name: str = "EVA02_Large"
    general_threshold: float = 0.35
    character_threshold: float = 0.85
    no_underline: bool = True
    drop_overlap: bool = True
    exclude_tags: tuple[str, ...] = ()
    vram_flush_every: int = 32


# ─────────────────────────────────────────────
# ⑧ 重複除去 (CCIP 埋め込みによる知覚的 dedup)
# ─────────────────────────────────────────────
@dataclass
class DedupConfig:
    """CCIP 埋め込みを使った kept クロップ間の重複除去設定。
    
    max_distance: これ以下の距離のペアは「ほぼ同じ」として片方を捨てる。
    embed_batch_size: CCIP 推論のバッチサイズ。
    """
    max_distance: float = 0.08
    embed_batch_size: int = 64


# ─────────────────────────────────────────────
# まとめ: 全設定を一つにまとめた Thresholds
# ─────────────────────────────────────────────
@dataclass
class Thresholds:
    """パイプライン全体の設定をまとめたルートデータクラス。
    
    project.json の "thresholds" キーとして保存・読み込みする。
    """
    scene: SceneConfig = field(default_factory=SceneConfig)
    detect: DetectConfig = field(default_factory=DetectConfig)
    track: TrackConfig = field(default_factory=TrackConfig)
    identify: IdentifyConfig = field(default_factory=IdentifyConfig)
    frame_select: FrameSelectConfig = field(default_factory=FrameSelectConfig)
    crop: CropConfig = field(default_factory=CropConfig)
    tag: TagConfig = field(default_factory=TagConfig)
    dedup: DedupConfig = field(default_factory=DedupConfig)

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def from_json(cls, path: Path) -> "Thresholds":
        data = json.loads(path.read_text())
        tag_raw = data.get("tag", {})
        return cls(
            scene=SceneConfig(**_filter_known(SceneConfig, data.get("scene", {}))),
            detect=DetectConfig(**_filter_known(DetectConfig, data.get("detect", {}))),
            track=TrackConfig(**_filter_known(TrackConfig, data.get("track", {}))),
            identify=IdentifyConfig(**_filter_known(IdentifyConfig, data.get("identify", {}))),
            frame_select=FrameSelectConfig(
                **_filter_known(FrameSelectConfig, data.get("frame_select", {}))
            ),
            crop=CropConfig(**_filter_known(CropConfig, data.get("crop", {}))),
            tag=TagConfig(**{
                **_filter_known(TagConfig, tag_raw),
                "exclude_tags": tuple(tag_raw.get("exclude_tags", ())),
            }),
            dedup=DedupConfig(**_filter_known(DedupConfig, data.get("dedup", {}))),
        )
