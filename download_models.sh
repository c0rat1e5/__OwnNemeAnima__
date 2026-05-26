#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# download_models.sh — 学習・タグ付けに必要な全モデルをダウンロードする
#
# ■ ダウンロードするもの:
#   [タグ付け]
#     ① WD14 EVA02-Large v3  (imgutils / HuggingFace 自動 DL → ~/.cache/huggingface/)
#     ② CCIP                 (imgutils / HuggingFace 自動 DL → ~/.cache/huggingface/)
#
#   [学習 (Anima LoRA)]
#     ③ anima-base-v1.0.safetensors  ← Anima DiT (transformer 本体)
#     ④ qwen_3_06b_base.safetensors  ← Qwen3 0.6B テキストエンコーダー
#     ⑤ qwen_image_vae.safetensors   ← Qwen Image VAE
#
#   [学習フレームワーク]
#     ⑥ diffusion-pipe       ← git clone (tdrussell/diffusion-pipe)
#
# ■ 保存先:
#   ~/models/
#   ├── anima/
#   │   ├── anima-base-v1.0.safetensors
#   │   ├── qwen_3_06b_base.safetensors
#   │   └── qwen_image_vae.safetensors
#   └── diffusion-pipe/
#       (学習フレームワーク本体)
#
# ■ 使い方:
#   ./download_models.sh             全部ダウンロード
#   ./download_models.sh tag         タグ付けモデルだけ
#   ./download_models.sh anima       Animaモデルだけ
#   ./download_models.sh pipe        diffusion-pipeだけ
# ────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── カラー出力 ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${CYAN}[info]${NC}  $*"; }
success() { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
error()   { echo -e "${RED}[error]${NC} $*" >&2; }
step()    { echo -e "\n${YELLOW}━━━ $* ━━━${NC}"; }

# ── パス設定 ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/backend/.venv/bin/python"

MODELS_DIR="${MODELS_DIR:-$HOME/models}"        # 変更したい場合は環境変数で上書き可
ANIMA_DIR="$MODELS_DIR/anima"
PIPE_DIR="$MODELS_DIR/diffusion-pipe"

# HuggingFace Hub のリポジトリID
HF_ANIMA_REPO="circlestone-labs/Anima"

# ── 前提チェック ──────────────────────────────────────────────────────────
check_requirements() {
    local ok=true

    if [[ ! -f "$VENV_PYTHON" ]]; then
        error ".venv が見つかりません: $VENV_PYTHON"
        error "先に: cd backend && python -m venv .venv && .venv/bin/pip install -e '.[dev]'"
        ok=false
    fi

    if ! command -v git &>/dev/null; then
        error "git がインストールされていません"
        ok=false
    fi

    if [[ "$ok" == "false" ]]; then exit 1; fi

    # huggingface-cli の確認
    if ! "$VENV_PYTHON" -m huggingface_hub.cli --help &>/dev/null 2>&1; then
        info "huggingface_hub をインストール中..."
        "$SCRIPT_DIR/backend/.venv/bin/pip" install -q huggingface_hub hf_xet
    fi
}

# ── ① & ② WD14 / CCIP (タグ付け・重複除去モデル) ──────────────────────
download_tag_models() {
    step "① WD14 EVA02-Large v3  &  ② CCIP  (タグ付け用)"

    info "WD14 タガー (SmilingWolf/wd-eva02-large-tagger-v3) をダウンロード中..."
    info "保存先: ~/.cache/huggingface/hub/"
    info "※ 約 3.5GB / 初回のみ時間がかかります"

    "$VENV_PYTHON" - <<'PYEOF'
import sys
print("  imgutils をロード中...")
try:
    # WD14 モデルを事前ダウンロード (1x1 の偽画像で空振りさせる)
    from PIL import Image
    import numpy as np
    dummy = Image.fromarray(np.zeros((64, 64, 3), dtype='uint8'))

    print("  WD14 モデルをダウンロード中 (初回は数分かかります)...")
    from imgutils.tagging import get_wd14_tags
    get_wd14_tags(dummy, model_name='EVA02_Large')
    print("  ✓ WD14 EVA02-Large v3: ダウンロード完了")
except Exception as e:
    print(f"  [warn] WD14: {e}", file=sys.stderr)

try:
    print("  CCIP モデルをダウンロード中...")
    from PIL import Image
    import numpy as np
    dummy = Image.fromarray(np.zeros((64, 64, 3), dtype='uint8'))
    from imgutils.metrics import ccip_extract_feature
    ccip_extract_feature(dummy)
    print("  ✓ CCIP: ダウンロード完了")
except Exception as e:
    print(f"  [warn] CCIP: {e}", file=sys.stderr)

print("  キャッシュ場所: ~/.cache/huggingface/hub/")
PYEOF

    success "タグ付けモデル: 完了"
}

# ── ③④⑤ Anima モデル ─────────────────────────────────────────────────────
download_anima_models() {
    step "③ anima-base-v1.0  ④ qwen_3_06b_base  ⑤ qwen_image_vae"

    mkdir -p "$ANIMA_DIR"
    info "保存先: $ANIMA_DIR"
    info "HuggingFace リポジトリ: $HF_ANIMA_REPO"
    info "※ 合計 約 5-8GB"

    local hf_cli="$SCRIPT_DIR/backend/.venv/bin/hf"

    # ③ Anima DiT (transformer 本体)
    local anima_safetensors="$ANIMA_DIR/anima-base-v1.0.safetensors"
    if [[ -f "$anima_safetensors" ]]; then
        warn "③ anima-base-v1.0.safetensors: すでに存在 → スキップ"
    else
        info "③ anima-base-v1.0.safetensors をダウンロード中..."
        "$hf_cli" download "$HF_ANIMA_REPO" \
            "split_files/diffusion_models/anima-base-v1.0.safetensors" \
            --local-dir "$ANIMA_DIR"
        # サブディレクトリから直下に移動
        mv -f "$ANIMA_DIR/split_files/diffusion_models/anima-base-v1.0.safetensors" \
               "$ANIMA_DIR/anima-base-v1.0.safetensors" 2>/dev/null || true
        success "③ anima-base-v1.0.safetensors: 完了"
    fi

    # ④ Qwen3 0.6B テキストエンコーダー
    local qwen_te="$ANIMA_DIR/qwen_3_06b_base.safetensors"
    if [[ -f "$qwen_te" ]]; then
        warn "④ qwen_3_06b_base.safetensors: すでに存在 → スキップ"
    else
        info "④ qwen_3_06b_base.safetensors をダウンロード中..."
        "$hf_cli" download "$HF_ANIMA_REPO" \
            "split_files/text_encoders/qwen_3_06b_base.safetensors" \
            --local-dir "$ANIMA_DIR"
        mv -f "$ANIMA_DIR/split_files/text_encoders/qwen_3_06b_base.safetensors" \
               "$ANIMA_DIR/qwen_3_06b_base.safetensors" 2>/dev/null || true
        success "④ qwen_3_06b_base.safetensors: 完了"
    fi

    # ⑤ Qwen Image VAE
    local qwen_vae="$ANIMA_DIR/qwen_image_vae.safetensors"
    if [[ -f "$qwen_vae" ]]; then
        warn "⑤ qwen_image_vae.safetensors: すでに存在 → スキップ"
    else
        info "⑤ qwen_image_vae.safetensors をダウンロード中..."
        "$hf_cli" download "$HF_ANIMA_REPO" \
            "split_files/vae/qwen_image_vae.safetensors" \
            --local-dir "$ANIMA_DIR"
        mv -f "$ANIMA_DIR/split_files/vae/qwen_image_vae.safetensors" \
               "$ANIMA_DIR/qwen_image_vae.safetensors" 2>/dev/null || true
        success "⑤ qwen_image_vae.safetensors: 完了"
    fi
    # 空になった split_files ディレクトリを削除
    rm -rf "$ANIMA_DIR/split_files" 2>/dev/null || true

    success "Anima モデル: 完了"
}

# ── ⑥ diffusion-pipe ─────────────────────────────────────────────────────
download_diffusion_pipe() {
    step "⑥ diffusion-pipe (学習フレームワーク)"

    if [[ -d "$PIPE_DIR/.git" ]]; then
        warn "⑥ diffusion-pipe: すでに存在 → git pull で更新"
        git -C "$PIPE_DIR" pull
        git -C "$PIPE_DIR" submodule update --init --recursive
    else
        info "クローン先: $PIPE_DIR"
        mkdir -p "$MODELS_DIR"
        git clone --recurse-submodules \
            https://github.com/tdrussell/diffusion-pipe \
            "$PIPE_DIR"
    fi

    # diffusion-pipe 専用の venv をセットアップ
    if [[ ! -f "$PIPE_DIR/.venv/bin/python" ]]; then
        info "diffusion-pipe の venv をセットアップ中..."
        python3 -m venv "$PIPE_DIR/.venv"
        "$PIPE_DIR/.venv/bin/pip" install -q torch torchvision \
            --index-url https://download.pytorch.org/whl/cu124
        "$PIPE_DIR/.venv/bin/pip" install -q -r "$PIPE_DIR/requirements.txt"
        success "diffusion-pipe venv: セットアップ完了"
    else
        warn "diffusion-pipe venv: すでに存在 → スキップ"
    fi

    success "diffusion-pipe: 完了"
}

# ── パスサマリーを表示 ─────────────────────────────────────────────────────
show_summary() {
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  ダウンロード完了！${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  [タグ付けモデル]"
    echo "  WD14 / CCIP: ~/.cache/huggingface/hub/ (自動管理)"
    echo ""
    echo "  [Anima モデル]  → Settings タブで以下を設定"
    echo "  anima_dit_path         : $ANIMA_DIR/anima-base-v1.0.safetensors"
    echo "  qwen_vae_path          : $ANIMA_DIR/qwen_image_vae.safetensors"
    echo "  qwen_text_encoder_path : $ANIMA_DIR/qwen_3_06b_base.safetensors"
    echo "  diffusion_pipe_dir     : $PIPE_DIR"
    echo ""
    echo -e "${CYAN}  ヒント: Settings タブ → Training セクションでパスを入力してください${NC}"
    echo ""
}

# ── メイン ────────────────────────────────────────────────────────────────
MODE="${1:-all}"

check_requirements

case "$MODE" in
    tag)
        download_tag_models
        ;;
    anima)
        download_anima_models
        show_summary
        ;;
    pipe)
        download_diffusion_pipe
        show_summary
        ;;
    all|*)
        download_tag_models
        download_anima_models
        download_diffusion_pipe
        show_summary
        ;;
esac
