"""
server/registry.py — プロジェクトの登録簿 (SQLite)。

■ なぜ SQLite？
  プロジェクト本体のデータは project.json に入っているが、
  「どのフォルダにプロジェクトがあるか」を管理するために
  軽量な SQLite を使う (~/.neme-anima/db.sqlite)。
  
  プロジェクト一覧 API がここから slug → path のマッピングを取得し、
  各プロジェクトの project.json を読み込んで返す。

■ テーブル設計:
  projects(slug TEXT PRIMARY KEY, root TEXT NOT NULL)
  - slug: URL-safe なプロジェクト識別子 (例: "megumin")
  - root: プロジェクトフォルダの絶対パス
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from neme_anima.storage.project import Project


class ProjectRegistry:
    """SQLite を使ったプロジェクト登録簿。

    サーバー起動時に一度インスタンスを作り、app.state.registry に保持する。
    全メソッドは同期的 (SQLite は同期 I/O)。FastAPI の async ハンドラーからは
    run_in_executor 経由で呼ぶか、直接呼んでも問題ない (I/O が速いため)。
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """スレッドセーフな接続を返す (check_same_thread=False)。
        
        FastAPI は複数スレッドで動くので、接続をスレッド間で共有せず
        呼び出しごとに新規接続する (SQLite は軽量なので問題なし)。
        """
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # dict ライクなアクセスを可能にする
        return conn

    def _init_db(self) -> None:
        """テーブルが存在しない場合のみ作成する (idempotent)。"""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    slug TEXT PRIMARY KEY,
                    root TEXT NOT NULL
                )
            """)

    # ────────── CRUD ──────────

    def register(self, project: Project) -> None:
        """プロジェクトを登録簿に追加 (すでにある場合は上書き)。"""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO projects (slug, root) VALUES (?, ?)",
                (project.slug, str(project.root)),
            )

    def unregister(self, slug: str) -> None:
        """登録簿からプロジェクトを削除する (ディスクは消さない)。"""
        with self._connect() as conn:
            conn.execute("DELETE FROM projects WHERE slug = ?", (slug,))

    def get(self, slug: str) -> Project | None:
        """slug からプロジェクトを取得する。見つからなければ None。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT root FROM projects WHERE slug = ?", (slug,)
            ).fetchone()
        if row is None:
            return None
        root = Path(row["root"])
        if not (root / "project.json").exists():
            # ディスク上に project.json がない → 孤立した登録を削除
            self.unregister(slug)
            return None
        return Project.load(root)

    def list_all(self) -> list[Project]:
        """登録されている全プロジェクトを返す。

        project.json が消えているものは自動的に登録簿から除外する。
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT slug, root FROM projects").fetchall()

        projects = []
        to_remove = []
        for row in rows:
            root = Path(row["root"])
            if not (root / "project.json").exists():
                to_remove.append(row["slug"])
                continue
            try:
                projects.append(Project.load(root))
            except Exception:
                # 壊れた project.json は無視してログだけ残す
                to_remove.append(row["slug"])

        for slug in to_remove:
            self.unregister(slug)

        return projects
