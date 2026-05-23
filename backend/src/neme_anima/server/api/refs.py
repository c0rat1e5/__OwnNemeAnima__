"""
server/api/refs.py — 参照画像のアップロード・削除。

エンドポイント:
  GET    /api/projects/{slug}/characters/{char_slug}/refs
  POST   /api/projects/{slug}/characters/{char_slug}/refs  (multipart upload)
  DELETE /api/projects/{slug}/refs/{ref_filename}
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(tags=["refs"])


def _get_project(request: Request, slug: str):
    project = request.app.state.registry.get(slug)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project not found: {slug}")
    return project


@router.get("/api/projects/{slug}/characters/{char_slug}/refs")
async def list_refs(slug: str, char_slug: str, request: Request) -> list[dict]:
    """キャラクターの参照画像一覧を返す。"""
    project = _get_project(request, slug)
    char = project.character_by_slug(char_slug)
    if char is None:
        raise HTTPException(status_code=404, detail=f"character not found: {char_slug}")
    return [{"path": r.path, "added_at": r.added_at} for r in char.refs]


@router.post("/api/projects/{slug}/characters/{char_slug}/refs", status_code=201)
async def upload_ref(
    slug: str, char_slug: str, file: UploadFile, request: Request
) -> dict:
    """参照画像をアップロードして refs/ に保存する。"""
    project = _get_project(request, slug)
    if project.character_by_slug(char_slug) is None:
        raise HTTPException(status_code=404, detail=f"character not found: {char_slug}")
    data = await file.read()
    ref = project.add_ref_bytes(
        file.filename or "ref.png",
        data,
        character_slug=char_slug,
    )
    return {"path": ref.path, "added_at": ref.added_at}


@router.delete("/api/projects/{slug}/refs/{ref_filename}", status_code=204)
async def delete_ref(slug: str, ref_filename: str, request: Request) -> None:
    """参照画像を全キャラクターから削除してディスクからも消す。"""
    project = _get_project(request, slug)
    # セキュリティ: ファイル名にパス区切り文字が入っていないか確認
    if "/" in ref_filename or "\\" in ref_filename or ".." in ref_filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    ref_path = str(project.root / "refs" / ref_filename)
    project.remove_ref(ref_path)


@router.get("/api/projects/{slug}/refs/{ref_filename}")
async def get_ref_image(slug: str, ref_filename: str, request: Request) -> FileResponse:
    """参照画像ファイルを返す (UI サムネイル表示用)。"""
    project = _get_project(request, slug)
    if "/" in ref_filename or "\\" in ref_filename or ".." in ref_filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = project.root / "refs" / ref_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="ref not found")
    return FileResponse(path)
