"""
config.py — タグ付けパイプラインの設定値。

■ 残したもの (使うもの):
  - CropConfig   : 画像リサイズ (任意)
  - TagConfig    : WD14 タグ付け
  - DedupConfig  : 重複除去

■ 削除したもの (動画パイプライン用だった):
  - SceneConfig / DetectConfig / TrackConfig / IdentifyConfig / FrameSelectConfig
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def _filter_known(dc_cls: type, raw: dict) -> dict:
    """知らないキーを無視して dataclass に渡せる dict を返す。"""
    declared = {f.name for f in fields(dc_cls)}
    return {k: v for k, v in raw.items() if k in declared}


# ─────────────────────────────────────────────
# クロップ (任意: 画像サイズを揃えたいとき)
# ─────────────────────────────────────────────
@dataclass
class CropConfig:
    """画像リサイズの設定。
    
    longest_side: 出力画像の長辺 px (デフォルト 1024)。
    pad_ratio:    バウンディングボックス周囲のパディング割合。
    """
    longest_side: int = 1024
    pad_ratio: float = 0.10


# ─────────────────────────────────────────────
# WD14 タグ付け
# ─────────────────────────────────────────────
@dataclass
class TagConfig:
    """WD14 Danbooru タグ付けの設定。

    model_name:          imgutils で使うモデル名 (EVA02_Large 推奨)。
    general_threshold:   一般タグの信頼スコア下限。高いほどタグが絞られる。
    character_threshold: キャラクタータグの信頼スコア下限。
    no_underline:        アンダースコア → スペース変換 (例: long_hair → long hair)。
    drop_overlap:        上位概念と重複するタグを削除。
    exclude_tags:        常に除外するタグ。
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
# 重複除去 (CCIP 埋め込みベース)
# ─────────────────────────────────────────────
@dataclass
class DedupConfig:
    """CCIP 埋め込みを使った知覚的重複除去設定。

    max_distance:    この距離以下のペアを「ほぼ同じ」と判定して片方を rejected/ へ。
    embed_batch_size: CCIP 推論のバッチサイズ。
    """
    max_distance: float = 0.08
    embed_batch_size: int = 64


# ─────────────────────────────────────────────
# まとめ
# ─────────────────────────────────────────────
@dataclass
class Thresholds:
    """全設定をまとめたルートクラス。thresholds.json として保存・読み込みする。"""
    crop:  CropConfig  = field(default_factory=CropConfig)
    tag:   TagConfig   = field(default_factory=TagConfig)
    dedup: DedupConfig = field(default_factory=DedupConfig)

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def from_json(cls, path: Path) -> "Thresholds":
        data = json.loads(path.read_text())
        tag_raw = data.get("tag", {})
        return cls(
            crop=CropConfig(**_filter_known(CropConfig, data.get("crop", {}))),
            tag=TagConfig(**{
                **_filter_known(TagConfig, tag_raw),
                "exclude_tags": tuple(tag_raw.get("exclude_tags", ())),
            }),
            dedup=DedupConfig(**_filter_known(DedupConfig, data.get("dedup", {}))),
        )
