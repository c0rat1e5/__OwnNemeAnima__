"""
server/job_progress.py — パイプライン進捗を追跡して SSE でフロントに届ける。

■ 流れ:
  1. パイプラインの各ステージ (detect, track, ...) が
     progress.update(stage, current, total) を呼ぶ
  2. JobProgress が Event を作って Broadcaster.publish() に渡す
  3. Broadcaster が全 SSE クライアントに配信
  4. フロントエンドの EventSource が受け取ってプログレスバーを更新

■ ステージ一覧:
  extract: scenes → detect → track → identify → select → crop → tag → dedup
  rerun:   identify → select → crop → tag → dedup  (検出・追跡をスキップ)
"""

from __future__ import annotations

import asyncio
from typing import Any

from neme_anima.server.events import Broadcaster, Event

# 抽出パイプラインの全ステージ (順番通り)
EXTRACT_STAGES = [
    "scenes",    # PySceneDetect でシーン分割
    "detect",    # YOLO でキャラクター検出
    "track",     # ByteTrack でトラッキング
    "identify",  # CCIP でキャラクター識別
    "select",    # フレーム選択
    "crop",      # クロップ
    "tag",       # WD14 タグ付け
    "dedup",     # 重複除去
]

# 再実行 (閾値変更時): 検出・追跡はキャッシュを使うのでスキップ
RERUN_STAGES = [
    "identify",
    "select",
    "crop",
    "tag",
    "dedup",
]


class JobProgress:
    """パイプラインの進捗状態を持ち、更新のたびに SSE イベントを発火する。

    パイプライン関数はこのオブジェクトを受け取り、
    各ステージで update() を呼ぶだけでいい。
    SSE の詳細は気にしなくてよい。
    """

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        broadcaster: Broadcaster,
        job_id: str,
        project_slug: str,
        source_idx: int,
        kind: str,       # "extract" | "rerun"
        stages: list[str],
    ) -> None:
        self._loop = loop
        self._broadcaster = broadcaster
        self.job_id = job_id
        self.project_slug = project_slug
        self.source_idx = source_idx
        self.kind = kind
        self.stages = stages

        # 現在の状態
        self.stage: str = stages[0] if stages else ""
        self.stage_current: int = 0
        self.stage_total: int = 0
        self.overall_pct: float = 0.0

    def publish_initial(self) -> None:
        """ジョブ開始時の「queued」イベントを発火する。"""
        self._emit("job_queued", {
            "job_id": self.job_id,
            "project_slug": self.project_slug,
            "source_idx": self.source_idx,
            "kind": self.kind,
            "stages": self.stages,
        })

    def update(
        self,
        stage: str,
        current: int,
        total: int,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """ステージの進捗を更新して SSE イベントを発火する。

        Args:
            stage:   現在処理中のステージ名 (EXTRACT_STAGES のいずれか)
            current: ステージ内の現在の処理数
            total:   ステージ内の総処理数
            extra:   追加情報 (任意)
        """
        self.stage = stage
        self.stage_current = current
        self.stage_total = total

        # 全体進捗率を計算 (ステージ番号 / 総ステージ数 + ステージ内進捗)
        stage_idx = self.stages.index(stage) if stage in self.stages else 0
        n = len(self.stages)
        if n > 0:
            stage_pct = (current / total) if total > 0 else 0.0
            self.overall_pct = (stage_idx + stage_pct) / n * 100.0

        data: dict[str, Any] = {
            "job_id": self.job_id,
            "project_slug": self.project_slug,
            "source_idx": self.source_idx,
            "stage": stage,
            "current": current,
            "total": total,
            "overall_pct": round(self.overall_pct, 1),
        }
        if extra:
            data.update(extra)
        self._emit("progress", data)

    def done(self, *, kept: int = 0, rejected: int = 0) -> None:
        """パイプライン完了イベントを発火する。"""
        self._emit("job_done", {
            "job_id": self.job_id,
            "project_slug": self.project_slug,
            "source_idx": self.source_idx,
            "kept": kept,
            "rejected": rejected,
        })

    def error(self, message: str) -> None:
        """エラーイベントを発火する。"""
        self._emit("job_error", {
            "job_id": self.job_id,
            "project_slug": self.project_slug,
            "source_idx": self.source_idx,
            "message": message,
        })

    def _emit(self, event_name: str, data: dict[str, Any]) -> None:
        """スレッドセーフに Broadcaster.publish を呼ぶ。
        
        パイプラインはスレッドプール上で動くので、
        asyncio のイベントループに call_soon_threadsafe で投げる。
        """
        event = Event(event=event_name, data=data)
        self._loop.call_soon_threadsafe(
            self._broadcaster._publish_sync, event
        )
