"""
server/training_runner.py — diffusion-pipe サブプロセスの管理。

■ 設計:
  TrainingManager は asyncio.subprocess で diffusion-pipe を起動し、
  stdout/stderr を SSE 経由でフロントエンドにストリーム配信する。
  
  一度に走る学習は 1 つだけ (GPU は 1 枚想定)。
  start() を呼ぶと既存の実行中プロセスがあれば拒否する。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from neme_anima.server.events import Broadcaster, Event

logger = logging.getLogger(__name__)


class TrainingManager:
    """diffusion-pipe サブプロセスを管理するコーディネーター。"""

    def __init__(self, broadcaster: Broadcaster) -> None:
        self._broadcaster = broadcaster
        self._proc: asyncio.subprocess.Process | None = None
        self._job_id: str | None = None
        self._project_slug: str | None = None
        self._character_slug: str | None = None
        self._started_at: datetime | None = None
        self._log_task: asyncio.Task | None = None

    def status(self) -> dict:
        """現在の学習状態を返す。"""
        if self._proc is None or self._proc.returncode is not None:
            return {"running": False, "job_id": None}
        return {
            "running": True,
            "job_id": self._job_id,
            "project_slug": self._project_slug,
            "character_slug": self._character_slug,
            "started_at": self._started_at.isoformat() if self._started_at else None,
        }

    async def start(self, *, project, character_slug: str) -> str:
        """LoRA 学習を開始する。既に実行中なら ValueError を送出。"""
        if self._proc is not None and self._proc.returncode is None:
            raise ValueError("学習はすでに実行中です")

        char = project.character_by_slug(character_slug)
        if char is None:
            raise KeyError(f"character not found: {character_slug}")

        cfg = char.training

        # diffusion-pipe の TOML 設定を生成
        toml_path = await asyncio.to_thread(
            self._write_toml, project, char, cfg
        )

        # サブプロセス起動
        python = str(
            Path(cfg.diffusion_pipe_dir) / ".venv" / "bin" / "python"
        )
        cmd = [
            python,
            "-m", "train",
            "--config", str(toml_path),
        ]

        self._job_id = str(uuid.uuid4())
        self._project_slug = project.slug
        self._character_slug = character_slug
        self._started_at = datetime.now(timezone.utc)

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cfg.diffusion_pipe_dir,
        )

        # ログを SSE にストリーム
        self._log_task = asyncio.create_task(
            self._stream_logs(), name="training-log"
        )

        self._broadcaster.publish(Event(
            event="training_start",
            data={
                "job_id": self._job_id,
                "project_slug": project.slug,
                "character_slug": character_slug,
            },
        ))

        logger.info(
            "training.start job=%s project=%s char=%s",
            self._job_id, project.slug, character_slug,
        )
        return self._job_id

    async def stop(self) -> None:
        """実行中の学習プロセスを停止する。"""
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                self._proc.kill()
            logger.info("training.stop job=%s", self._job_id)

    async def shutdown(self) -> None:
        """サーバーシャットダウン時に呼ぶ。"""
        await self.stop()
        if self._log_task:
            self._log_task.cancel()

    async def _stream_logs(self) -> None:
        """stdout を読んで SSE でブロードキャストする。"""
        if self._proc is None or self._proc.stdout is None:
            return
        try:
            async for line in self._proc.stdout:
                text = line.decode(errors="replace").rstrip()
                self._broadcaster.publish(Event(
                    event="training_log",
                    data={
                        "job_id": self._job_id,
                        "line": text,
                    },
                ))
        except Exception:
            pass
        finally:
            rc = await self._proc.wait()
            self._broadcaster.publish(Event(
                event="training_done",
                data={
                    "job_id": self._job_id,
                    "returncode": rc,
                },
            ))
            logger.info("training.done job=%s rc=%d", self._job_id, rc)

    def _write_toml(self, project, char, cfg) -> Path:
        """diffusion-pipe 用の TOML 設定ファイルを生成する。"""
        import tomllib  # Python 3.11+

        runs_dir = project.training_runs_dir / char.slug
        runs_dir.mkdir(parents=True, exist_ok=True)
        output_dir = runs_dir / "output"
        output_dir.mkdir(exist_ok=True)
        dataset_dir = runs_dir / "dataset"
        dataset_dir.mkdir(exist_ok=True)

        # データセットディレクトリを組み立て (staging は別途必要)
        toml_content = f"""
[model]
type = "flux"
checkpoint_path = "{cfg.anima_dit_path}"
vae_path = "{cfg.qwen_vae_path}"
text_encoder_path = "{cfg.qwen_text_encoder_path}"

[training]
output_dir = "{output_dir}"
batch_size = {cfg.batch_size}
num_epochs = {cfg.epochs}
lr = {cfg.lr}
save_every_n_epochs = {cfg.save_every_n_epochs}
keep_last_n_checkpoints = {cfg.keep_last_n_checkpoints}

[lora]
rank = {cfg.rank}
alpha = {cfg.alpha}

[[dataset]]
directory = "{dataset_dir}"
""".strip()

        toml_path = runs_dir / "config.toml"
        toml_path.write_text(toml_content)
        return toml_path
