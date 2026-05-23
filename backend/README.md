# Neme-Anima Backend

アニメキャラクターの LoRA 学習データをビデオから自動抽出する Python バックエンド。

## 起動方法

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/neme-anima ui
```

## パイプライン

1. **PySceneDetect** — 動画をシーンに分割
2. **DeepGHS YOLO (imgutils)** — キャラクター検出
3. **ByteTrack** — フレーム間トラッキング
4. **CCIP** — キャラクター識別 (参照画像と照合)
5. **フレーム選択** — シャープネス・視認性でベストフレームを選ぶ
6. **クロップ** — 長辺 1024px でクロップ
7. **WD14 タグ付け** — Danbooru タグ + kohya `.txt` 生成
8. **重複除去** — CCIP で near-duplicate を reject
