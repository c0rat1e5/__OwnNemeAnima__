"""
server/api/ws.py — SSE (Server-Sent Events) エンドポイント。

■ なぜ WebSocket でなく SSE？
  - 一方向 (サーバー → クライアント) の通知だけなので SSE で十分。
  - HTTP/1.1 で動く、プロキシ透過性が高い、クライアント側実装が簡単。
  - フロントエンド: new EventSource('/api/events') だけで接続できる。

エンドポイント:
  GET /api/events   → SSE ストリーム (全プロジェクトのイベントを受け取る)
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["events"])


@router.get("/api/events")
async def sse_stream(request: Request) -> StreamingResponse:
    """SSE ストリームを開く。

    クライアントが切断するまでイベントを流し続ける。
    各イベントは以下の形式:
      event: progress
      data: {"job_id": "...", "stage": "detect", "overall_pct": 42.0}
      
      (空行でイベント終端)
    """
    broadcaster = request.app.state.broadcaster

    async def generate():
        # 接続確立を知らせるハートビート
        yield "event: connected\ndata: {}\n\n"
        async for event in broadcaster.subscribe():
            # クライアントが切断していたら停止
            if await request.is_disconnected():
                break
            yield event.to_sse_text()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            # キャッシュ無効化
            "Cache-Control": "no-cache",
            # Nginx 等のバッファリングを無効化
            "X-Accel-Buffering": "no",
        },
    )
