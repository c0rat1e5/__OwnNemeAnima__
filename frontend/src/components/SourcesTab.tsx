"use client";

/**
 * components/SourcesTab.tsx — ビデオと参照画像の管理タブ。
 *
 * ■ 機能:
 *   - ビデオファイルのパス追加・削除
 *   - 参照画像のドラッグ&ドロップアップロード・削除
 *   - 各ビデオに対して「抽出開始」ボタン
 *   - 抽出中の進捗バー表示
 */

import { useEffect, useState, useCallback, useRef } from "react";
import { api, type Source, type Project } from "@/lib/api";
import type { ProgressState } from "@/app/page";
import { basename, cn } from "@/lib/utils";

interface SourcesTabProps {
  project: Project;
  progress: Record<string, ProgressState>;
  onRefresh: () => void;
}

export function SourcesTab({ project, progress, onRefresh }: SourcesTabProps) {
  const [sources, setSources] = useState<Source[]>([]);
  const [refs, setRefs] = useState<Record<string, { path: string; added_at: string }[]>>({});
  const [newVideoPath, setNewVideoPath] = useState("");
  const [activeCharSlug, setActiveCharSlug] = useState(
    project.characters[0]?.slug ?? "default"
  );
  const fileInputRef = useRef<HTMLInputElement>(null);

  // このプロジェクトの進捗
  const runningProgress = Object.values(progress).find(
    (p) => p.projectSlug === project.slug
  );

  const fetchSources = useCallback(async () => {
    const list = await api.listSources(project.slug);
    setSources(list);
  }, [project.slug]);

  const fetchRefs = useCallback(async (charSlug: string) => {
    try {
      const list = await api.listRefs(project.slug, charSlug);
      setRefs((prev) => ({ ...prev, [charSlug]: list }));
    } catch {
      setRefs((prev) => ({ ...prev, [charSlug]: [] }));
    }
  }, [project.slug]);

  useEffect(() => {
    fetchSources();
    for (const char of project.characters) {
      fetchRefs(char.slug);
    }
  }, [fetchSources, fetchRefs, project.characters]);

  const handleAddVideo = async () => {
    if (!newVideoPath.trim()) return;
    try {
      await api.addSource(project.slug, newVideoPath.trim());
      setNewVideoPath("");
      fetchSources();
    } catch (err) {
      alert(`追加失敗: ${err}`);
    }
  };

  const handleRemoveVideo = async (idx: number) => {
    if (!confirm("このビデオを削除しますか？")) return;
    await api.removeSource(project.slug, idx);
    fetchSources();
  };

  const handleExtract = async (idx: number) => {
    try {
      await api.startExtract(project.slug, idx);
    } catch (err) {
      alert(`抽出開始失敗: ${err}`);
    }
  };

  const handleRerun = async (idx: number) => {
    try {
      await api.startRerun(project.slug, idx);
    } catch (err) {
      alert(`再実行失敗: ${err}`);
    }
  };

  const handleRefUpload = async (files: FileList | null) => {
    if (!files) return;
    for (const file of Array.from(files)) {
      try {
        await api.uploadRef(project.slug, activeCharSlug, file);
      } catch (err) {
        alert(`アップロード失敗: ${err}`);
      }
    }
    fetchRefs(activeCharSlug);
  };

  const handleDeleteRef = async (filename: string) => {
    await api.deleteRef(project.slug, filename);
    fetchRefs(activeCharSlug);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    handleRefUpload(e.dataTransfer.files);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* ── ビデオセクション ── */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">ビデオソース</h2>

        {/* 追加フォーム */}
        <div className="flex gap-2 mb-4">
          <input
            className="flex-1 rounded bg-bg-surface border border-bg-border px-3 py-2 text-sm placeholder-text-muted outline-none focus:border-accent"
            placeholder="ビデオファイルのパス (例: /home/user/anime/ep01.mkv)"
            value={newVideoPath}
            onChange={(e) => setNewVideoPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddVideo()}
          />
          <button
            onClick={handleAddVideo}
            className="rounded bg-accent px-4 py-2 text-sm font-medium hover:bg-accent-hover"
          >
            追加
          </button>
        </div>

        {/* 全体進捗バー */}
        {runningProgress && (
          <div className="mb-4 rounded-lg border border-bg-border bg-bg-surface p-3">
            <div className="flex justify-between text-xs text-text-secondary mb-1">
              <span>ステージ: {runningProgress.stage}</span>
              <span>{Math.round(runningProgress.overall_pct)}%</span>
            </div>
            <div className="h-2 rounded-full bg-bg-border">
              <div
                className="h-2 rounded-full bg-accent transition-all duration-300"
                style={{ width: `${runningProgress.overall_pct}%` }}
              />
            </div>
            <div className="mt-1 text-xs text-text-muted">
              {runningProgress.current} / {runningProgress.total}
            </div>
          </div>
        )}

        {/* ビデオリスト */}
        {sources.length === 0 ? (
          <p className="text-sm text-text-muted">
            ビデオが追加されていません。
          </p>
        ) : (
          <div className="space-y-2">
            {sources.map((src, idx) => {
              const isRunning =
                runningProgress?.sourceIdx === idx;
              return (
                <div
                  key={idx}
                  className="flex items-center gap-3 rounded-lg border border-bg-border bg-bg-surface p-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="truncate text-sm font-medium">
                      {basename(src.path)}
                    </div>
                    <div className="text-xs text-text-muted">
                      {src.path}
                    </div>
                    {src.extraction_runs.length > 0 && (
                      <div className="mt-1 text-xs text-text-secondary">
                        抽出済み {src.extraction_runs.length} 回
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => handleExtract(idx)}
                      disabled={!!runningProgress}
                      className={cn(
                        "rounded px-3 py-1.5 text-xs font-medium",
                        runningProgress
                          ? "bg-bg-border text-text-muted cursor-not-allowed"
                          : "bg-accent hover:bg-accent-hover"
                      )}
                    >
                      {isRunning ? "実行中..." : "抽出"}
                    </button>
                    {src.extraction_runs.length > 0 && (
                      <button
                        onClick={() => handleRerun(idx)}
                        disabled={!!runningProgress}
                        className="rounded border border-bg-border px-3 py-1.5 text-xs hover:border-accent hover:text-accent disabled:opacity-50"
                      >
                        再実行
                      </button>
                    )}
                    <button
                      onClick={() => handleRemoveVideo(idx)}
                      className="rounded px-3 py-1.5 text-xs text-text-muted hover:text-red-400"
                    >
                      削除
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ── 参照画像セクション ── */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">参照画像</h2>

        {/* キャラクタータブ */}
        {project.characters.length > 1 && (
          <div className="flex gap-2 mb-3">
            {project.characters.map((c) => (
              <button
                key={c.slug}
                onClick={() => {
                  setActiveCharSlug(c.slug);
                  fetchRefs(c.slug);
                }}
                className={cn(
                  "rounded-full px-3 py-1 text-sm",
                  activeCharSlug === c.slug
                    ? "bg-accent text-white"
                    : "bg-bg-surface border border-bg-border text-text-secondary hover:border-accent"
                )}
              >
                {c.name}
              </button>
            ))}
          </div>
        )}

        {/* ドラッグ&ドロップゾーン */}
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => fileInputRef.current?.click()}
          className="mb-4 flex h-24 cursor-pointer items-center justify-center rounded-lg border-2 border-dashed border-bg-border hover:border-accent transition-colors"
        >
          <p className="text-sm text-text-muted">
            参照画像をドロップ or クリックでアップロード
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => handleRefUpload(e.target.files)}
          />
        </div>

        {/* 参照画像グリッド */}
        <div className="grid grid-cols-6 gap-2">
          {(refs[activeCharSlug] ?? []).map((ref) => {
            const filename = basename(ref.path);
            return (
              <div key={ref.path} className="group relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/api/projects/${project.slug}/refs/${filename}`}
                  alt={filename}
                  className="aspect-square w-full rounded object-cover"
                />
                <button
                  onClick={() => handleDeleteRef(filename)}
                  className="absolute right-1 top-1 hidden rounded bg-black/70 px-1.5 py-0.5 text-xs text-white group-hover:block hover:bg-red-500"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
