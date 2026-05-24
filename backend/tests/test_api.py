"""
tests/test_api.py — FastAPI エンドポイントのテスト。

■ テスト戦略:
  httpx.AsyncClient + TestClient でリアルな HTTP リクエストを送り、
  レスポンスを検証する。
  DB/ファイルは一時ディレクトリを使うので本番環境を汚さない。

■ 学習ポイント:
  - FastAPI の TestClient は httpx のラッパー
  - pytest の tmp_path フィクスチャで一時ディレクトリを自動作成・削除
  - create_app(state_dir=...) にテスト用ディレクトリを渡すことで分離できる
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from neme_anima.server.app import create_app


# ─────────────────────────────────────────────
# フィクスチャ: テスト用アプリ + クライアント
# ─────────────────────────────────────────────

@pytest.fixture
def tmp_state(tmp_path: Path) -> Path:
    """テスト用のサーバー状態ディレクトリ。"""
    state = tmp_path / "server_state"
    state.mkdir()
    return state


@pytest.fixture
def client(tmp_state: Path):
    """テスト用の FastAPI TestClient。
    
    with ブロックで lifespan (起動・停止処理) が正しく実行される。
    """
    app = create_app(state_dir=tmp_state)
    with TestClient(app) as c:
        yield c


# ─────────────────────────────────────────────
# ① ヘルスチェック
# ─────────────────────────────────────────────

def test_health(client):
    """GET /api/health が {"ok": True} を返すこと。"""
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


# ─────────────────────────────────────────────
# ② プロジェクト CRUD
# ─────────────────────────────────────────────

def test_list_projects_empty(client):
    """プロジェクトが 0 件のとき空リストを返すこと。"""
    res = client.get("/api/projects")
    assert res.status_code == 200
    assert res.json() == []


def test_create_and_get_project(client, tmp_path: Path):
    """プロジェクト作成 → 一覧取得 → 詳細取得の流れ。"""
    root = tmp_path / "test_project"

    # 作成
    res = client.post("/api/projects", json={"root": str(root), "name": "TestChar"})
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "TestChar"
    assert data["slug"] == "test_project"  # フォルダ名がスラグになる
    assert len(data["characters"]) == 1
    assert data["characters"][0]["slug"] == "default"

    slug = data["slug"]

    # 一覧
    res = client.get("/api/projects")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # 詳細
    res = client.get(f"/api/projects/{slug}")
    assert res.status_code == 200
    assert res.json()["slug"] == slug

    # project.json がディスクに作成されているか確認
    assert (root / "project.json").is_file()
    with open(root / "project.json") as f:
        pj = json.load(f)
    assert pj["name"] == "TestChar"


def test_create_project_duplicate(client, tmp_path: Path):
    """同じパスに 2 回プロジェクト作成すると 409 になること。"""
    root = tmp_path / "dup_project"
    client.post("/api/projects", json={"root": str(root), "name": "A"})
    res = client.post("/api/projects", json={"root": str(root), "name": "B"})
    assert res.status_code == 409


def test_delete_project(client, tmp_path: Path):
    """プロジェクト削除後に一覧から消えること。"""
    root = tmp_path / "to_delete"
    res = client.post("/api/projects", json={"root": str(root), "name": "Del"})
    slug = res.json()["slug"]

    res = client.delete(f"/api/projects/{slug}")
    assert res.status_code == 204

    # 登録簿から消えている
    res = client.get("/api/projects")
    assert res.json() == []

    # ディスクのファイルは残っている
    assert (root / "project.json").is_file()


# ─────────────────────────────────────────────
# ③ Settings エンドポイント
# ─────────────────────────────────────────────

def test_get_settings_default(client, tmp_path: Path):
    """thresholds.json がないとき、デフォルト値を返すこと。"""
    root = tmp_path / "settings_test"
    res = client.post("/api/projects", json={"root": str(root), "name": "S"})
    slug = res.json()["slug"]

    res = client.get(f"/api/projects/{slug}/settings")
    assert res.status_code == 200
    body = res.json()
    assert "thresholds" in body
    assert "llm" in body
    # デフォルト閾値のチェック
    assert body["thresholds"]["crop"]["longest_side"] == 1024
    assert body["thresholds"]["tag"]["general_threshold"] == 0.35
    # LLM はデフォルト無効
    assert body["llm"]["enabled"] is False


def test_patch_settings(client, tmp_path: Path):
    """Settings PATCH が値を更新して thresholds.json に保存すること。"""
    root = tmp_path / "patch_test"
    res = client.post("/api/projects", json={"root": str(root), "name": "P"})
    slug = res.json()["slug"]

    # タグ閾値を変更
    res = client.patch(
        f"/api/projects/{slug}/settings",
        json={"thresholds": {"tag": {"general_threshold": 0.5}}},
    )
    assert res.status_code == 200
    assert res.json()["thresholds"]["tag"]["general_threshold"] == 0.5

    # thresholds.json に書き込まれているか
    cfg_path = root / "thresholds.json"
    assert cfg_path.is_file()
    cfg = json.loads(cfg_path.read_text())
    assert cfg["tag"]["general_threshold"] == 0.5

    # LLM 有効化
    res = client.patch(
        f"/api/projects/{slug}/settings",
        json={"llm": {"enabled": True, "model": "llama3"}},
    )
    assert res.status_code == 200
    assert res.json()["llm"]["enabled"] is True
    assert res.json()["llm"]["model"] == "llama3"


# ─────────────────────────────────────────────
# ④ 画像アップロード
# ─────────────────────────────────────────────

def test_upload_frame(client, tmp_path: Path):
    """画像アップロードで kept/ に保存され、metadata.jsonl に登録されること。"""
    root = tmp_path / "upload_test"
    res = client.post("/api/projects", json={"root": str(root), "name": "Up"})
    slug = res.json()["slug"]

    tiny_png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01"
        b"\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00"
        b"\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    res = client.post(
        f"/api/projects/{slug}/frames",
        files={"file": ("test.png", tiny_png, "image/png")},
    )
    assert res.status_code == 201
    assert res.json()["filename"] == "test.png"
    assert res.json()["character_slug"] == "default"

    # ファイルが kept/ にあるか
    assert (root / "output" / "kept" / "test.png").is_file()

    # 一覧に出てくるか
    res = client.get(f"/api/projects/{slug}/frames")
    assert res.status_code == 200
    assert len(res.json()) == 1


# ─────────────────────────────────────────────
# ⑤ キャラクター管理
# ─────────────────────────────────────────────

def test_add_and_remove_character(client, tmp_path: Path):
    """キャラクター追加・削除。"""
    root = tmp_path / "char_test"
    res = client.post("/api/projects", json={"root": str(root), "name": "Multi"})
    slug = res.json()["slug"]

    # 追加
    res = client.post(
        f"/api/projects/{slug}/characters",
        json={"name": "Megumin"},
    )
    assert res.status_code == 201
    assert res.json()["slug"] == "megumin"

    # 詳細にキャラクターが 2 人
    res = client.get(f"/api/projects/{slug}")
    assert len(res.json()["characters"]) == 2

    # 削除
    res = client.delete(f"/api/projects/{slug}/characters/megumin")
    assert res.status_code == 204

    res = client.get(f"/api/projects/{slug}")
    assert len(res.json()["characters"]) == 1


def test_remove_last_character_fails(client, tmp_path: Path):
    """最後の 1 人を削除しようとすると 400 になること。"""
    root = tmp_path / "last_char"
    res = client.post("/api/projects", json={"root": str(root), "name": "Solo"})
    slug = res.json()["slug"]
    char_slug = res.json()["characters"][0]["slug"]

    res = client.delete(f"/api/projects/{slug}/characters/{char_slug}")
    assert res.status_code == 400
