"""
server/queue.py — 抽出・再実行ジョブの非同期キュー。

■ 設計思想:
  パイプライン (GPU 処理) はスレッドプールで実行し、
  FastAPI の async ループをブロックしないようにする。
  
  ジョブは FIFO で順番に処理される (並列実行なし)。
  UI からの「抽出開始」リクエストは即座に job_id を返し、
  処理はバックグラウンドで進行する。進捗は SSE で通知。

■ ジョブの状態遷移:
  queued → running → done / error
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

JobRunner = Callable[[str, dict[str, Any]], None]
"""ジョブ実行関数の型。(job_id, payload) を受け取り、例外を投げる可能性がある。"""


@dataclass
class Job:
    """キュー内の一ジョブを表す。
    
    kind:    "extract" | "rerun"
    payload: ルーターから渡される追加情報 (project_slug, source_idx 等)
    """
    id: str
    kind: str
    payload: dict[str, Any]
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str = "queued"   # "queued" | "running" | "done" | "error"
    error: str | None = None


class JobQueue:
    """FIFO ジョブキュー。

    使い方:
      queue = JobQueue(runner=my_runner)
      await queue.start()   # バックグラウンドワーカー起動
      job_id = queue.enqueue("extract", {"project_slug": "megumin", ...})
      # ... SSE で進捗を受け取りながら待つ ...
      await queue.stop()    # シャットダウン
    """

    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._jobs: dict[str, Job] = {}   # job_id → Job (最近の履歴を保持)
        self._worker_task: asyncio.Task | None = None

    def enqueue(self, kind: str, payload: dict[str, Any]) -> str:
        """新しいジョブをキューに積み、job_id を返す。"""
        job_id = str(uuid.uuid4())
        job = Job(id=job_id, kind=kind, payload=payload)
        self._jobs[job_id] = job
        self._queue.put_nowait(job)
        logger.info("job.enqueue id=%s kind=%s", job_id, kind)
        return job_id

    def get_job(self, job_id: str) -> Job | None:
        """job_id からジョブ情報を取得する。"""
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        """全ジョブ一覧を返す (最新順)。"""
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    async def start(self) -> None:
        """バックグラウンドワーカータスクを起動する。"""
        self._worker_task = asyncio.create_task(self._worker(), name="job-worker")

    async def stop(self) -> None:
        """ワーカーを停止する。現在実行中のジョブは完了を待たない。"""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _worker(self) -> None:
        """キューからジョブを取り出してランナーを呼ぶワーカーループ。
        
        asyncio.to_thread でスレッドプールに移譲するので
        GPU ヘビーな処理も async ループをブロックしない。
        """
        logger.info("job worker started")
        while True:
            job = await self._queue.get()
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            logger.info("job.start id=%s kind=%s", job.id, job.kind)
            try:
                # GPU 処理はスレッドプールで実行
                await asyncio.to_thread(self._runner, job.id, job.payload)
                job.status = "done"
            except Exception as exc:
                job.status = "error"
                job.error = str(exc)
                logger.exception("job.error id=%s", job.id)
            finally:
                job.finished_at = datetime.now(timezone.utc)
                self._queue.task_done()
                logger.info("job.finish id=%s status=%s", job.id, job.status)
