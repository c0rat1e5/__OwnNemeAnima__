"""
storage/project.py — プロジェクトの全データモデルとファイル I/O。

■ プロジェクトフォルダのレイアウト:

    ~/neme-projects/megumin/
      project.json          ← プロジェクト全体の設定を JSON で保存
      refs/                 ← キャラクターの参照画像
        .thumbnails/        ← UI 表示用サムネイルのキャッシュ
      output/
        kept/               ← アップロード済み画像 + タグ .txt
        rejected/           ← 除外した画像
        metadata.jsonl      ← 各フレームのメタデータ (character_slug 等)

■ マルチキャラクター対応:
    プロジェクトは複数の Character を持てる。
    kept/ フォルダはフラットで、metadata.jsonl の character_slug で
    どのキャラクターか判別する。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CHARACTER_SLUG = "default"


def _slugify_character_name(name: str) -> str:
    """文字列を URL/ファイル名安全なスラッグに変換する。
    
    例: "Megumin (Konosuba)" → "megumin-konosuba"
    空文字の場合は "character" を返す。
    """
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "")).strip("-").lower()
    return s or "character"


# ─────────────────────────────────────────────
# RefImage: キャラクターの参照画像
# ─────────────────────────────────────────────
@dataclass
class RefImage:
    """キャラクター識別 (CCIP) に使う参照画像。
    
    path: refs/ フォルダ内の絶対パス。
    added_at: ISO-8601 UTC タイムスタンプ。
    """
    path: str       # refs/ フォルダ内の絶対パス
    added_at: str   # ISO-8601 UTC


# ─────────────────────────────────────────────
# LLMConfig: 自然言語キャプション生成の設定
# ─────────────────────────────────────────────
@dataclass
class LLMConfig:
    """OpenAI 互換 API を使ったキャプション生成の設定。
    
    enabled=False のときは WD14 タグのみで、LLM キャプションは生成しない。
    endpoint: OpenAI 互換 API の URL (LM Studio, OpenRouter, vLLM 等)。
    api_key: 空文字 = Authorization ヘッダーなし (LM Studio のデフォルト)。
    """
    enabled: bool = False
    endpoint: str = "http://localhost:1234"
    model: str = ""
    prompt: str = ""    # 空 = llm.DEFAULT_PROMPT を使用
    api_key: str = ""   # 空 = Authorization ヘッダーなし


# ─────────────────────────────────────────────
# TrainingConfig: Anima LoRA 学習の設定
# ─────────────────────────────────────────────
@dataclass
class TrainingConfig:
    """Anima LoRA 学習設定 (tdrussell/diffusion-pipe に渡す TOML を生成するために使う)。
    
    ■ パスグループ (実在するパスが必要):
      diffusion_pipe_dir: diffusion-pipe のクローン先
      anima_dit_path:     Anima の DiT チェックポイント
      qwen_vae_path:      Qwen VAE チェックポイント
      qwen_text_encoder_path: Qwen テキストエンコーダー
    
    ■ ハイパーパラメータ:
      rank / alpha: LoRA のランクと alpha (alpha/rank = 実効学習率スケール)
      lr: 学習率
      epochs: エポック数
      batch_size: バッチサイズ
    
    ■ キャプション設定:
      trigger_token: LoRA のトリガーワード (空 = なし)
      core_tag_pruning_enabled: よく出るタグをキャプションから除く
      core_tag_threshold: X% 以上のフレームに出るタグをコアタグと判定
    """
    preset: str = "style"

    # --- パスグループ ---
    diffusion_pipe_dir: str = ""
    anima_dit_path: str = ""
    qwen_vae_path: str = ""
    qwen_text_encoder_path: str = ""

    # --- ハイパーパラメータ ---
    rank: int = 32
    alpha: float = 16.0
    lr: float = 1e-4
    epochs: int = 10
    batch_size: int = 1
    save_every_n_epochs: int = 1
    keep_last_n_checkpoints: int = 3   # 0 = 全部保持

    # --- キャプション・データセット設定 ---
    trigger_token: str = ""
    core_tag_pruning_enabled: bool = False
    core_tag_threshold: float = 0.35
    repeat_multiplier: float = 0.0     # 0.0 = 自動 (フレーム数から計算)


# ─────────────────────────────────────────────
# Character: プロジェクト内の一キャラクター
# ─────────────────────────────────────────────
@dataclass
class Character:
    """プロジェクト内の一キャラクター。
    
    slug: ファイル名・辞書キーに使う安全な識別子 (例: "megumin")。
    name: UI 表示用の名前 (例: "Megumin")。
    refs: このキャラクターの参照画像リスト。
    training: このキャラクターの LoRA 学習設定。
    """
    slug: str
    name: str
    refs: list[RefImage] = field(default_factory=list)
    trigger_token: str = ""
    training: TrainingConfig = field(default_factory=TrainingConfig)


# ─────────────────────────────────────────────
# Project: プロジェクト全体
# ─────────────────────────────────────────────
@dataclass
class Project:
    """プロジェクト全体を表すルートデータクラス。
    
    project.json への読み書きメソッド、
    ソース/参照画像の追加・削除メソッドを持つ。
    """
    name: str
    slug: str
    root: Path
    created_at: datetime
    characters: list[Character] = field(default_factory=list)
    llm: LLMConfig = field(default_factory=LLMConfig)

    # ────────── 保存 ──────────

    def save(self) -> None:
        """プロジェクトの状態を project.json に書き出す。"""
        data = {
            "name": self.name,
            "slug": self.slug,
            "created_at": self.created_at.isoformat(),
            "characters": [
                {
                    "slug": c.slug,
                    "name": c.name,
                    "trigger_token": c.trigger_token,
                    "refs": [asdict(r) for r in c.refs],
                    "training": asdict(c.training),
                }
                for c in self.characters
            ],
            "llm": asdict(self.llm),
        }
        (self.root / "project.json").write_text(json.dumps(data, indent=2))

    # ────────── 生成・読み込み ──────────

    @classmethod
    def create(cls, root: Path, *, name: str) -> "Project":
        """新規プロジェクトをディスクに作成して返す。
        
        root が既に存在する場合は ValueError を送出する。
        """
        root = Path(root).resolve()
        if root.exists():
            raise ValueError(f"既に存在します: {root}")
        slug = root.name
        now = datetime.now(timezone.utc)
        project = cls(
            name=name,
            slug=slug,
            root=root,
            created_at=now,
            # 最初から 1 つのデフォルトキャラクターを作る
            characters=[Character(slug=DEFAULT_CHARACTER_SLUG, name=name)],
        )
        # フォルダ骨格を作成
        (root / "refs" / ".thumbnails").mkdir(parents=True)
        (root / "output" / "kept").mkdir(parents=True)
        (root / "output" / "rejected").mkdir(parents=True)
        (root / "output" / "cache").mkdir(parents=True)
        project.save()
        return project

    @classmethod
    def load(cls, root: Path) -> "Project":
        """project.json からプロジェクトを読み込む。"""
        root = Path(root)
        with open(root / "project.json") as f:
            data = json.load(f)

        llm_raw = data.get("llm") or {}
        characters = cls._load_characters(data)

        return cls(
            name=str(data.get("name", root.name)),
            slug=str(data.get("slug", root.name)),
            root=root,
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now(timezone.utc).isoformat())
            ),
            characters=characters,
            llm=LLMConfig(
                enabled=bool(llm_raw.get("enabled", False)),
                endpoint=str(llm_raw.get("endpoint", "http://localhost:1234")),
                model=str(llm_raw.get("model", "")),
                prompt=str(llm_raw.get("prompt", "")),
                api_key=str(llm_raw.get("api_key", "")),
            ),
        )

    @staticmethod
    def _load_characters(data: dict) -> list[Character]:
        """project.json の characters フィールドをパースする。
        
        古い形式 (top-level refs / training) にも対応し、
        自動的に "default" キャラクターに移行する。
        """
        if "characters" in data and data["characters"]:
            chars: list[Character] = []
            for raw in data["characters"]:
                training_raw = raw.get("training") or {}
                training = TrainingConfig(**{
                    f.name: training_raw[f.name]
                    for f in fields(TrainingConfig())
                    if f.name in training_raw
                })
                chars.append(Character(
                    slug=str(raw.get("slug") or DEFAULT_CHARACTER_SLUG),
                    name=str(raw.get("name") or raw.get("slug") or "Character"),
                    trigger_token=str(raw.get("trigger_token") or ""),
                    refs=[RefImage(**r) for r in raw.get("refs", [])],
                    training=training,
                ))
            return chars

        # 古い形式: top-level refs → default キャラクターに変換
        refs = [RefImage(**r) for r in data.get("refs", [])]
        training_raw = data.get("training") or {}
        training = TrainingConfig(**{
            f.name: training_raw[f.name]
            for f in fields(TrainingConfig())
            if f.name in training_raw
        })
        return [Character(
            slug=DEFAULT_CHARACTER_SLUG,
            name=str(data.get("name", "Character")),
            refs=refs,
            training=training,
        )]


    # ────────── キャラクター操作 ──────────

    def character_by_slug(self, slug: str) -> Character | None:
        for c in self.characters:
            if c.slug == slug:
                return c
        return None

    def add_character(self, *, name: str, slug: str | None = None) -> Character:
        """新しいキャラクターをプロジェクトに追加する。
        
        slug はすでに存在する場合、末尾に -2, -3, ... を付けてユニークにする。
        """
        base = _slugify_character_name(slug or name)
        candidate = base
        n = 2
        existing = {c.slug for c in self.characters}
        while candidate in existing:
            candidate = f"{base}-{n}"
            n += 1
        char = Character(slug=candidate, name=name)
        self.characters.append(char)
        self.save()
        return char

    def remove_character(self, slug: str) -> None:
        if len(self.characters) <= 1:
            raise ValueError("プロジェクトには最低 1 つのキャラクターが必要です")
        self.characters = [c for c in self.characters if c.slug != slug]
        self.save()

    def _resolve_character(self, slug: str | None) -> Character:
        """slug が None なら最初のキャラクターを返す。存在しない slug は KeyError。"""
        if slug is None:
            if not self.characters:
                self.characters = [
                    Character(slug=DEFAULT_CHARACTER_SLUG, name=self.name)
                ]
            return self.characters[0]
        c = self.character_by_slug(slug)
        if c is None:
            raise KeyError(f"unknown character slug: {slug!r}")
        return c


    # ────────── 参照画像操作 ──────────

    def add_ref(
        self, ref_path: Path, *, character_slug: str | None = None
    ) -> RefImage:
        """外部の参照画像を refs/ にコピーして追加する。"""
        ref_path = Path(ref_path)
        if not ref_path.is_file():
            raise FileNotFoundError(ref_path)
        return self._ingest_ref(
            ref_path.name, ref_path.read_bytes(), character_slug=character_slug
        )

    def add_ref_bytes(
        self, filename: str, data: bytes, *, character_slug: str | None = None
    ) -> RefImage:
        """アップロードされたバイト列を refs/ に保存して追加する。"""
        return self._ingest_ref(filename, data, character_slug=character_slug)

    def _ingest_ref(
        self, filename: str, data: bytes, *, character_slug: str | None = None
    ) -> RefImage:
        character = self._resolve_character(character_slug)
        dest = self._unique_ref_path(filename)
        dest.write_bytes(data)
        ref = RefImage(
            path=str(dest),
            added_at=datetime.now(timezone.utc).isoformat(),
        )
        character.refs.append(ref)
        self.save()
        return ref

    def _unique_ref_path(self, filename: str) -> Path:
        """refs/ フォルダ内でユニークなパスを生成する。"""
        name = Path(filename).name or "ref"
        dest = self.root / "refs" / name
        if not dest.exists():
            return dest
        stem, suffix = dest.stem, dest.suffix
        for n in range(2, 10_000):
            candidate = self.root / "refs" / f"{stem}-{n}{suffix}"
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"refs/ に {name!r} のコピーが多すぎます")

    def remove_ref(self, ref_path: str) -> None:
        """全キャラクターから参照画像を削除し、ディスクからも消す。"""
        for character in self.characters:
            character.refs = [r for r in character.refs if r.path != ref_path]
        p = Path(ref_path)
        if p.is_file():
            p.unlink()
        self.save()



    # ────────── パスヘルパー ──────────


    @property
    def kept_dir(self) -> Path:
        return self.root / "output" / "kept"

    @property
    def rejected_dir(self) -> Path:
        return self.root / "output" / "rejected"

    @property
    def metadata_path(self) -> Path:
        return self.root / "output" / "metadata.jsonl"


    @property
    def training_dir(self) -> Path:
        return self.root / "training"

    @property
    def training_runs_dir(self) -> Path:
        return self.training_dir / "runs"


# ────────── ユーティリティ ──────────

def is_under_refs(candidate: Path, project_root: Path) -> bool:
    """パスがプロジェクトの refs/ フォルダ以下かどうか確認する。"""
    try:
        candidate.resolve().relative_to((project_root / "refs").resolve())
        return True
    except (ValueError, OSError):
        return False
