#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# start.sh — OwnNemeAnima 起動スクリプト
#
# 使い方:
#   ./start.sh          バックエンド + フロントエンドを両方起動
#   ./start.sh backend  バックエンドだけ起動
#   ./start.sh frontend フロントエンドだけ起動
#   ./start.sh stop     起動中のプロセスを停止
# ────────────────────────────────────────────────────────────────

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"

BACKEND_PID_FILE="$ROOT/.backend.pid"
FRONTEND_PID_FILE="$ROOT/.frontend.pid"

# ── カラー出力 ──────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}[info]${NC}  $*"; }
success() { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
error()   { echo -e "${RED}[error]${NC} $*" >&2; }

# ── バックエンド起動 ────────────────────────────────────────────
start_backend() {
    info "バックエンド (FastAPI) を起動中..."

    if [[ ! -f "$BACKEND_DIR/.venv/bin/python" ]]; then
        error ".venv が見つかりません: $BACKEND_DIR/.venv"
        error "先に: cd backend && python -m venv .venv && .venv/bin/pip install -e '.[dev]'"
        exit 1
    fi

    # すでに起動中なら何もしない
    if [[ -f "$BACKEND_PID_FILE" ]]; then
        local pid
        pid=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            warn "バックエンドはすでに起動中 (PID=$pid)"
            return
        fi
    fi

    cd "$BACKEND_DIR"
    nohup .venv/bin/python -m uvicorn \
        neme_anima.server.app:create_app \
        --factory \
        --host 127.0.0.1 \
        --port 8000 \
        --reload \
        > "$ROOT/.backend.log" 2>&1 &

    echo $! > "$BACKEND_PID_FILE"
    success "バックエンド起動 (PID=$(cat "$BACKEND_PID_FILE"))"
    success "  API:  http://127.0.0.1:8000"
    success "  Docs: http://127.0.0.1:8000/docs"
}

# ── フロントエンド起動 ──────────────────────────────────────────
start_frontend() {
    info "フロントエンド (Next.js) を起動中..."

    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        info "node_modules がないので npm install を実行中..."
        cd "$FRONTEND_DIR" && npm install
    fi

    # すでに起動中なら何もしない
    if [[ -f "$FRONTEND_PID_FILE" ]]; then
        local pid
        pid=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            warn "フロントエンドはすでに起動中 (PID=$pid)"
            return
        fi
    fi

    cd "$FRONTEND_DIR"
    nohup npm run dev \
        > "$ROOT/.frontend.log" 2>&1 &

    echo $! > "$FRONTEND_PID_FILE"
    success "フロントエンド起動 (PID=$(cat "$FRONTEND_PID_FILE"))"
    success "  UI: http://localhost:3000"
}

# ── 停止 ────────────────────────────────────────────────────────
stop_all() {
    info "停止中..."

    for pidfile in "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"; do
        if [[ -f "$pidfile" ]]; then
            local pid
            pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                success "停止: PID=$pid"
            else
                warn "プロセスはすでに停止済み: PID=$pid"
            fi
            rm -f "$pidfile"
        fi
    done

    # uvicorn の --reload は子プロセスを生むので pkill でまとめて片付ける
    pkill -f "uvicorn neme_anima" 2>/dev/null || true
    pkill -f "next dev"           2>/dev/null || true

    success "停止完了"
}

# ── ログ表示ヘルパー ────────────────────────────────────────────
show_logs() {
    echo ""
    echo "ログを確認する場合:"
    echo "  tail -f $ROOT/.backend.log"
    echo "  tail -f $ROOT/.frontend.log"
}

# ── メイン ──────────────────────────────────────────────────────
MODE="${1:-all}"

case "$MODE" in
    backend)
        start_backend
        show_logs
        ;;
    frontend)
        start_frontend
        show_logs
        ;;
    stop)
        stop_all
        ;;
    all|*)
        start_backend
        # バックエンドの起動を少し待つ
        sleep 2
        start_frontend
        echo ""
        info "─────────────────────────────────────"
        success "起動完了！"
        info "  フロントエンド: http://localhost:3000"
        info "  API Docs:       http://127.0.0.1:8000/docs"
        info "─────────────────────────────────────"
        show_logs
        echo ""
        info "停止するときは: ./start.sh stop"
        ;;
esac
