"use client";

/**
 * components/UploadTab.tsx — PNG 画像のアップロードとタグ付けの起動。
 *
 * ■ 機能:
 *   - ドラッグ&ドロップ (または クリック) で .png を kept/ にアップロード
 *   - アップロード完了後に「タグ付け開始」ボタンで WD14 を一括実行
 *   - 進捗バーは SSE で受け取る
 */

import { useCallback, useRef, useState } from "react";
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
  const fileInputRef = useRef<HTMLInputElement>(null);

  // このプロジェクトの進捗
  const runningProgress = Object.values(progress).find(
    (p) => p.projectSlug === project.slug
  );

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
    try {
      setError(null);
      await api.startTag(project.slug);
    } catch (err) {
      setError(String(err));
    }
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
      <div className="rounded-lg border border-bg-border bg-bg-surface p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold">WD14 タグ付け</h3>
            <p className="mt-0.5 text-xs text-text-muted">
              kept/ 内の全 PNG に自動タグ付けし、.txt を生成します
            </p>
          </div>
          <button
            onClick={handleStartTag}
            disabled={!!runningProgress}
            className={cn(
              "rounded px-4 py-2 text-sm font-medium transition-colors",
              runningProgress
                ? "bg-bg-border text-text-muted cursor-not-allowed"
                : "bg-accent hover:bg-accent-hover"
            )}
          >
            {runningProgress ? "実行中..." : "タグ付け開始"}
          </button>
        </div>

        {/* 進捗バー */}
        {runningProgress && (
          <div className="mt-3">
            <div className="flex justify-between text-xs text-text-secondary mb-1">
              <span>{runningProgress.stage}</span>
              <span>{Math.round(runningProgress.overall_pct)}%</span>
            </div>
            <div className="h-2 rounded-full bg-bg-border">
              <div
                className="h-2 rounded-full bg-accent transition-all duration-300"
                style={{ width: `${runningProgress.overall_pct}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-text-muted">
              {runningProgress.current} / {runningProgress.total}
            </p>
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
