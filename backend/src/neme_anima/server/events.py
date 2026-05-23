"""
server/events.py — Server-Sent Events (SSE) のブロードキャスター。

■ SSE とは？
  HTTP の一方向ストリーミング。サーバーからクライアントへ
  テキストイベントを流し続ける仕組み。WebSocket より軽い。
  フロントエンドは EventSource API で受け取る。

■ 設計:
  Broadcaster は非同期キューを使って複数のクライアントに
  同じイベントを配信する「ファンアウト」を実現する。
  
  クライアントが /api/events に接続すると subscribe() が呼ばれ、
  asyncio.Queue が払い出される。Broadcaster.publish() を呼ぶと
  全 Queue にメッセージが入り、ストリーム経由でクライアントに届く。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """SSE で送るイベント。
    
    event: イベント種別 (例: "progress", "done", "error")。
    data:  JSON シリアライズ可能な payload。
    """
    event: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse_text(self) -> str:
        """SSE 形式のテキストに変換する。
        
        形式:
          event: progress
          data: {"stage": "detect", "pct": 42}
          
          (空行でイベント終端)
        """
        return f"event: {self.event}\ndata: {json.dumps(self.data)}\n\n"


class Broadcaster:
    """複数のクライアントに同じイベントを配信するファンアウト機構。
    
    使い方:
      # サーバー起動時
      broadcaster = Broadcaster()
      
      # SSE エンドポイント
      async def sse_endpoint():
          async with broadcaster.subscribe() as queue:
              async for chunk in _sse_stream(queue):
                  yield chunk
      
      # パイプライン側
      broadcaster.publish(Event(event="progress", data={"pct": 50})
    """

    def __init__(self) -> None:
        # 接続中の全クライアントの Queue を持つ set
        self._subscribers: set[asyncio.Queue[Event | None]] = set()
        self._lock = asyncio.Lock()

    def publish(self, event: Event) -> None:
        """全クライアントにイベントをブロードキャストする (スレッドセーフ)。
        
        パイプラインはスレッドプール上で動くので、
        asyncio のイベントループに call_soon_threadsafe で投げる。
        """
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(self._publish_sync, event)

    def _publish_sync(self, event: Event) -> None:
        """イベントループ内で全 Queue に put する (同期, ループ内専用)。"""
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE queue full, dropping event: %s", event.event)

    async def subscribe(self) -> AsyncIterator[Event]:
        """クライアントが接続したときに呼ぶ。
        
        イベントを yield する非同期イテレータを返す。
        クライアントが切断すると自動的に登録解除される。
        
        使い方:
          async for event in broadcaster.subscribe():
              yield event.to_sse_text().encode()
        """
        queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers.add(queue)
        logger.debug("SSE client connected (total=%d)", len(self._subscribers))
        try:
            while True:
                event = await queue.get()
                if event is None:
                    # None はシャットダウンシグナル
                    break
                yield event
        finally:
            async with self._lock:
                self._subscribers.discard(queue)
            logger.debug(
                "SSE client disconnected (total=%d)", len(self._subscribers)
            )

    async def close_all(self) -> None:
        """全クライアントに None (終了シグナル) を送り、接続を閉じる。"""
        async with self._lock:
            for queue in self._subscribers:
                await queue.put(None)
