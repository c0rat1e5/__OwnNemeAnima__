"""
cli.py — neme-anima コマンドラインインターフェース。

使い方:
  neme-anima ui                         → Web UI を起動
  neme-anima project create <path> --name <name>
  neme-anima project add-video <project> <video>
  neme-anima project add-ref <project> <ref_image>
  neme-anima project extract <project>
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
import uvicorn

app = typer.Typer(name="neme-anima", help="アニメキャラクター LoRA ビルダー")
project_app = typer.Typer(help="プロジェクト管理コマンド")
app.add_typer(project_app, name="project")


@app.command()
def ui(
    host: str = typer.Option("127.0.0.1", help="バインドするホスト"),
    port: int = typer.Option(0, help="ポート番号 (0 = ランダム)"),
    state_dir: Optional[Path] = typer.Option(None, help="状態ディレクトリ"),
    log_level: str = typer.Option("info", help="ログレベル"),
) -> None:
    """Web UI サーバーを起動する。"""
    import socket
    from neme_anima.server.app import create_app

    logging.basicConfig(level=log_level.upper())

    fastapi_app = create_app(state_dir=state_dir)

    # ポート 0 の場合はランダムポートを割り当てる
    if port == 0:
        with socket.socket() as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

    url = f"http://{host}:{port}"
    typer.echo(f"neme-anima UI: {url}")

    # ブラウザを自動で開く
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run(fastapi_app, host=host, port=port, log_level=log_level)


@project_app.command("create")
def project_create(
    root: Path = typer.Argument(..., help="プロジェクトフォルダのパス"),
    name: str = typer.Option(..., help="プロジェクト名"),
    state_dir: Optional[Path] = typer.Option(None),
) -> None:
    """新しいプロジェクトを作成して登録簿に追加する。"""
    from neme_anima.server.app import default_state_dir
    from neme_anima.server.registry import ProjectRegistry
    from neme_anima.storage.project import Project

    sd = state_dir or default_state_dir()
    registry = ProjectRegistry(sd / "db.sqlite")
    project = Project.create(root.expanduser().resolve(), name=name)
    registry.register(project)
    typer.echo(f"✓ プロジェクト作成: {project.root}")


@project_app.command("add-video")
def project_add_video(
    project_root: Path = typer.Argument(...),
    video: Path = typer.Argument(...),
) -> None:
    """ビデオをプロジェクトに追加する。"""
    from neme_anima.storage.project import Project
    p = Project.load(project_root.expanduser().resolve())
    p.add_source(video.expanduser().resolve())
    typer.echo(f"✓ ビデオ追加: {video.name}")


@project_app.command("add-ref")
def project_add_ref(
    project_root: Path = typer.Argument(...),
    ref: Path = typer.Argument(...),
    character: Optional[str] = typer.Option(None, help="キャラクタースラッグ"),
) -> None:
    """参照画像をプロジェクトに追加する。"""
    from neme_anima.storage.project import Project
    p = Project.load(project_root.expanduser().resolve())
    p.add_ref(ref.expanduser().resolve(), character_slug=character)
    typer.echo(f"✓ 参照画像追加: {ref.name}")


@project_app.command("extract")
def project_extract(
    project_root: Path = typer.Argument(...),
    source_idx: int = typer.Option(0, help="ソースのインデックス"),
) -> None:
    """CLI から直接抽出パイプラインを実行する (GPU 必須)。"""
    from neme_anima.storage.project import Project
    from neme_anima.pipeline import run_extract
    from neme_anima.server.events import Broadcaster
    from neme_anima.server.job_progress import EXTRACT_STAGES, JobProgress
    import asyncio

    p = Project.load(project_root.expanduser().resolve())

    loop = asyncio.new_event_loop()
    broadcaster = Broadcaster()
    progress = JobProgress(
        loop=loop,
        broadcaster=broadcaster,
        job_id="cli",
        project_slug=p.slug,
        source_idx=source_idx,
        kind="extract",
        stages=EXTRACT_STAGES,
    )

    typer.echo(f"抽出開始: {p.sources[source_idx].path}")
    run_extract(project=p, source_idx=source_idx, progress=progress)
    typer.echo("✓ 抽出完了")
