"use client";

/**
 * app/page.tsx — アプリのメインページ。
 *
 * ■ 構造:
 *   左サイドバー: プロジェクト選択
 *   上タブバー:   Sources / Frames / Training / Settings
 *   メインエリア: 選択タブのコンテンツ
 *
 * ■ 状態管理:
 *   useState でシンプルに管理 (Redux 等は不要なスケール)。
 *   SSE は useEffect で購読し、進捗を state に反映する。
 */

import { useEffect, useState, useCallback } from "react";
import { api, connectSSE, type Project, type SSEEvent } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { TabBar, type TabId } from "@/components/TabBar";
import { UploadTab } from "@/components/UploadTab";
import { FramesTab } from "@/components/FramesTab";
import { TrainingTab } from "@/components/TrainingTab";
import { SettingsTab } from "@/components/SettingsTab";

// 進捗情報の型
export interface ProgressState {
  jobId: string;
  projectSlug: string;
  sourceIdx: number;
  stage: string;
  overall_pct: number;
  current: number;
  total: number;
}

export default function Home() {
  // ── 状態 ──────────────────────────────────────────────
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("upload");
  const [progress, setProgress] = useState<Record<string, ProgressState>>({});
  const [loading, setLoading] = useState(true);

  // 選択中プロジェクトのオブジェクト
  const selectedProject = projects.find((p) => p.slug === selectedSlug) ?? null;

  // ── プロジェクト一覧の取得 ──────────────────────────
  const fetchProjects = useCallback(async () => {
    try {
      const list = await api.listProjects();
      setProjects(list);
      // 最初のプロジェクトを自動選択
      if (list.length > 0 && !selectedSlug) {
        setSelectedSlug(list[0].slug);
      }
    } catch (err) {
      console.error("Failed to fetch projects:", err);
    } finally {
      setLoading(false);
    }
  }, [selectedSlug]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // ── SSE 購読 ───────────────────────────────────────
  useEffect(() => {
    const cleanup = connectSSE((e: SSEEvent) => {
      if (e.type === "progress") {
        const d = e.data as {
          job_id: string;
          project_slug: string;
          source_idx: number;
          stage: string;
          overall_pct: number;
          current: number;
          total: number;
        };
        setProgress((prev) => ({
          ...prev,
          [d.job_id]: {
            jobId: d.job_id,
            projectSlug: d.project_slug,
            sourceIdx: d.source_idx,
            stage: d.stage,
            overall_pct: d.overall_pct,
            current: d.current,
            total: d.total,
          },
        }));
      }
      if (e.type === "job_done" || e.type === "job_error") {
        const d = e.data as { job_id: string };
        setProgress((prev) => {
          const next = { ...prev };
          delete next[d.job_id];
          return next;
        });
        // 完了後にプロジェクト情報を再取得
        fetchProjects();
      }
    });
    return cleanup;
  }, [fetchProjects]);

  // ── プロジェクト作成 ────────────────────────────────
  const handleCreateProject = async (root: string, name: string) => {
    try {
      const project = await api.createProject(root, name);
      setProjects((prev) => [...prev, project]);
      setSelectedSlug(project.slug);
    } catch (err) {
      alert(`プロジェクト作成失敗: ${err}`);
    }
  };

  // ── レンダリング ────────────────────────────────────
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-text-secondary">読み込み中...</div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* 左サイドバー: プロジェクト選択 */}
      <Sidebar
        projects={projects}
        selectedSlug={selectedSlug}
        onSelect={setSelectedSlug}
        onCreateProject={handleCreateProject}
        progress={progress}
      />

      {/* メインエリア */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {selectedProject ? (
          <>
            {/* タブバー */}
            <TabBar activeTab={activeTab} onTabChange={setActiveTab} />

            {/* タブコンテンツ */}
            <main className="flex-1 overflow-auto p-4">
              {activeTab === "upload" && (
                <UploadTab
                  project={selectedProject}
                  progress={progress}
                  onRefresh={fetchProjects}
                  onNavigateToFrames={() => setActiveTab("frames")}
                />
              )}
              {activeTab === "frames" && (
                <FramesTab project={selectedProject} progress={progress} />
              )}
              {activeTab === "training" && (
                <TrainingTab project={selectedProject} />
              )}
              {activeTab === "settings" && (
                <SettingsTab
                  project={selectedProject}
                  onRefresh={fetchProjects}
                />
              )}
            </main>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center flex-col gap-4">
            <div className="text-4xl">🎬</div>
            <div className="text-text-secondary">
              左のサイドバーからプロジェクトを選択してください
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
