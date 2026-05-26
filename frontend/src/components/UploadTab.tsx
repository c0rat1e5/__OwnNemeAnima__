"use client";

/**
 * components/UploadTab.tsx — PNG 画像のアップロードとタグ付けの起動。
 *
 * ■ 機能:
 *   - ドラッグ&ドロップ (または クリック) で .png を kept/ にアップロード
 *   - アップロード完了後に「タグ付け開始」ボタンで WD14 を一括実行
 *   - 進捗バーは SSE で受け取る
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Project, type FrameMeta } from "@/lib/api";
import type { ProgressState } from "@/app/page";
import { cn } from "@/lib/utils";

interface UploadTabProps {
  project: Project;
  progress: Record<string, ProgressState>;
  onRefresh: () => void;
}

export function UploadTab({ project, progress, onRefresh }: UploadTabProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState<FrameMeta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [retag, setRetag] = useState(false);
  const [isTagging, setIsTagging] = useState(false);
  const [tagDone, setTagDone] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // このプロジェクトの SSE 進捗
  const runningProgress = Object.values(progress).find(
    (p) => p.projectSlug === project.slug
  );

  // isTagging か SSE 実行中のどちらかで「実行中」とみなす
  const isRunning = isTagging || !!runningProgress;

  // アンマウント時にポーリングを止める
  useEffect(() => () => { if (pollingRef.current) clearTimeout(pollingRef.current); }, []);

  const handleFiles = useCallback(
    async (files: File[]) => {
      const pngs = files.filter((f) =>
        f.name.toLowerCase().endsWith(".png")
      );
      if (pngs.length === 0) {
        setError("PNG ファイルのみ対応しています。");
        return;
      }
      setError(null);
      setUploading(true);
      try {
        const results = await api.uploadFrames(project.slug, pngs);
        setUploaded((prev) => [...prev, ...results]);
        onRefresh();
      } catch (err) {
        setError(String(err));
      } finally {
        setUploading(false);
      }
    },
    [project.slug, onRefresh]
  );

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(Array.from(e.dataTransfer.files));
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = () => setDragging(false);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      handleFiles(Array.from(e.target.files));
    }
    e.target.value = "";
  };

  const handleStartTag = async () => {
    if (pollingRef.current) clearTimeout(pollingRef.current);
    setError(null);
    setTagDone(false);
    setIsTagging(true);          // ← ボタンを押した瞬間に実行中 UI へ切替

    let jobId: string;
    try {
      const res = await api.startTag(project.slug, { retag });
      jobId = res.job_id;
    } catch (err) {
      setError(String(err));
      setIsTagging(false);
      return;
    }

    // ジョブ完了をポーリングで確実に検知
    const poll = async () => {
      try {
        const job = await api.getJob(jobId);
        if (job.status === "done") {
          setIsTagging(false);
          setTagDone(true);
          onRefresh();
          setTimeout(() => setTagDone(false), 4000);
        } else if (job.status === "error") {
          setIsTagging(false);
          setError(job.error ?? "タグ付けに失敗しました");
        } else {
          pollingRef.current = setTimeout(poll, 600);
        }
      } catch {
        pollingRef.current = setTimeout(poll, 1000);
      }
    };
    pollingRef.current = setTimeout(poll, 300);
  };

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      {/* ── エラー表示 ── */}
      {error && (
        <div className="rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* ── ドロップゾーン ── */}
      <div
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-12 text-center transition-colors cursor-pointer",
          dragging
            ? "border-accent bg-accent/10"
            : "border-bg-border hover:border-accent/60 bg-bg-surface"
        )}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
      >
        <svg
          className="h-10 w-10 text-text-muted"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
          />
        </svg>
        <div>
          <p className="text-sm font-medium text-text-primary">
            PNG をドラッグ&ドロップ
          </p>
          <p className="mt-1 text-xs text-text-muted">
            またはクリックしてファイルを選択
          </p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".png,image/png"
          multiple
          className="hidden"
          onChange={handleInputChange}
        />
      </div>

      {/* ── アップロード状態 ── */}
      {uploading && (
        <p className="text-sm text-text-secondary text-center">アップロード中...</p>
      )}

      {/* ── タグ付けセクション ── */}
      <div
        className={cn(
          "rounded-lg border p-4 transition-all duration-300",
          isRunning
            ? "border-accent bg-accent/5 shadow-[0_0_16px_2px_rgba(124,58,237,0.15)]"
            : tagDone
            ? "border-green-700 bg-green-950/30"
            : "border-bg-border bg-bg-surface"
        )}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            {/* ヘッダー行: タイトル + 実行中バッジ */}
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold">WD14 タグ付け</h3>
              {isRunning && (
                <span className="inline-flex items-center gap-1 rounded-full bg-accent/20 px-2 py-0.5 text-xs font-medium text-accent-light animate-pulse">
                  <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
                  </svg>
                  実行中
                </span>
              )}
              {tagDone && !isRunning && (
                <span className="inline-flex items-center gap-1 rounded-full bg-green-900/50 px-2 py-0.5 text-xs font-medium text-green-400">
                  <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414L8.414 15 3.293 9.879a1 1 0 111.414-1.414L8.414 12.172l6.879-6.879a1 1 0 011.414 0z" clipRule="evenodd"/>
                  </svg>
                  完了
                </span>
              )}
            </div>

            {/* サブテキスト */}
            {!isRunning && (
              <p className="mt-0.5 text-xs text-text-muted">
                kept/ 内の全 PNG に自動タグ付けし、.txt を生成します
              </p>
            )}
            {isRunning && (
              <p className="mt-0.5 text-xs text-accent-light/70">
                {runningProgress
                  ? <>ステージ: <span className="font-medium text-accent-light">{runningProgress.stage}</span>　{runningProgress.current} / {runningProgress.total} 枚</>
                  : "処理中..."}
              </p>
            )}

            {/* retag チェックボックス (非実行中のみ表示) */}
            {!isRunning && (
              <label className="mt-2 flex items-center gap-1.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={retag}
                  onChange={(e) => setRetag(e.target.checked)}
                  className="accent-accent"
                />
                <span className="text-xs text-text-secondary">既存タグを上書き (retag)</span>
              </label>
            )}
          </div>

          {/* ボタン */}
          <button
            onClick={handleStartTag}
            disabled={isRunning}
            className={cn(
              "shrink-0 rounded px-4 py-2 text-sm font-medium transition-all duration-200",
              isRunning
                ? "bg-bg-border text-text-muted cursor-not-allowed opacity-50"
                : "bg-accent hover:bg-accent-hover active:scale-95"
            )}
          >
            タグ付け開始
          </button>
        </div>

        {/* 進捗バー (SSE 実行中のみ) */}
        {runningProgress && (
          <div className="mt-4">
            <div className="flex justify-between text-xs text-text-secondary mb-1.5">
              <span className="text-accent-light/80">処理中...</span>
              <span className="font-mono font-medium text-accent-light">
                {Math.round(runningProgress.overall_pct)}%
              </span>
            </div>
            <div className="h-2.5 rounded-full bg-bg-border overflow-hidden">
              <div
                className="h-full rounded-full bg-accent transition-all duration-500 ease-out relative overflow-hidden"
                style={{ width: `${Math.max(runningProgress.overall_pct, 4)}%` }}
              >
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full animate-[shimmer_1.5s_infinite]" />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── 今回アップロードしたファイル一覧 ── */}
      {uploaded.length > 0 && (
        <div>
          <p className="mb-2 text-xs text-text-secondary">
            このセッションでアップロード: {uploaded.length} 枚
          </p>
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 lg:grid-cols-8">
            {uploaded.map((f) => (
              <div
                key={f.filename}
                className="relative aspect-square overflow-hidden rounded border border-bg-border bg-bg-surface"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/api/projects/${project.slug}/frames/${f.filename}`}
                  alt={f.filename}
                  className="h-full w-full object-cover"
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
