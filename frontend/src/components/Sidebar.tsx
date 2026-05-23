"use client";

/**
 * components/Sidebar.tsx — プロジェクト選択サイドバー。
 */

import { useState } from "react";
import { type Project } from "@/lib/api";
import { type ProgressState } from "@/app/page";
import { cn, basename } from "@/lib/utils";

interface SidebarProps {
  projects: Project[];
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
  onCreateProject: (root: string, name: string) => void;
  progress: Record<string, ProgressState>;
}

export function Sidebar({
  projects,
  selectedSlug,
  onSelect,
  onCreateProject,
  progress,
}: SidebarProps) {
  const [showCreate, setShowCreate] = useState(false);
  const [root, setRoot] = useState("");
  const [name, setName] = useState("");

  // このプロジェクトで実行中のジョブがあるか
  const runningSlug = Object.values(progress).find(
    (p) => p.projectSlug
  )?.projectSlug;

  const handleCreate = () => {
    if (!root || !name) return;
    onCreateProject(root, name);
    setRoot("");
    setName("");
    setShowCreate(false);
  };

  return (
    <aside className="flex h-full w-64 flex-col border-r border-bg-border bg-bg-surface">
      {/* ヘッダー */}
      <div className="flex items-center justify-between border-b border-bg-border px-4 py-3">
        <span className="font-semibold tracking-wide text-accent">
          Neme-Anima
        </span>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="rounded px-2 py-1 text-sm text-text-secondary hover:bg-bg-raised hover:text-text-primary"
          title="新規プロジェクト"
        >
          +
        </button>
      </div>

      {/* 新規プロジェクト作成フォーム */}
      {showCreate && (
        <div className="border-b border-bg-border p-3 space-y-2">
          <input
            className="w-full rounded bg-bg-raised px-2 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none focus:ring-1 focus:ring-accent"
            placeholder="プロジェクト名"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="w-full rounded bg-bg-raised px-2 py-1.5 text-sm text-text-primary placeholder-text-muted outline-none focus:ring-1 focus:ring-accent"
            placeholder="フォルダパス (例: ~/neme-projects/megumin)"
            value={root}
            onChange={(e) => setRoot(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              className="flex-1 rounded bg-accent py-1.5 text-sm font-medium hover:bg-accent-hover"
            >
              作成
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="flex-1 rounded bg-bg-raised py-1.5 text-sm text-text-secondary hover:text-text-primary"
            >
              キャンセル
            </button>
          </div>
        </div>
      )}

      {/* プロジェクト一覧 */}
      <nav className="flex-1 overflow-y-auto py-2">
        {projects.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-text-muted">
            + ボタンでプロジェクトを作成
          </p>
        ) : (
          projects.map((p) => {
            const isRunning = p.slug === runningSlug;
            const prog = Object.values(progress).find(
              (pr) => pr.projectSlug === p.slug
            );
            return (
              <button
                key={p.slug}
                onClick={() => onSelect(p.slug)}
                className={cn(
                  "w-full text-left px-4 py-2.5 hover:bg-bg-raised transition-colors",
                  selectedSlug === p.slug && "bg-bg-raised border-l-2 border-accent"
                )}
              >
                <div className="text-sm font-medium text-text-primary">
                  {p.name}
                </div>
                <div className="text-xs text-text-muted mt-0.5">
                  {p.characters.length} キャラクター ·{" "}
                  {p.source_count} ビデオ
                </div>
                {/* 進捗バー */}
                {isRunning && prog && (
                  <div className="mt-1.5">
                    <div className="text-xs text-accent-light mb-0.5">
                      {prog.stage} {Math.round(prog.overall_pct)}%
                    </div>
                    <div className="h-1 w-full rounded-full bg-bg-border">
                      <div
                        className="h-1 rounded-full bg-accent transition-all"
                        style={{ width: `${prog.overall_pct}%` }}
                      />
                    </div>
                  </div>
                )}
              </button>
            );
          })
        )}
      </nav>
    </aside>
  );
}
