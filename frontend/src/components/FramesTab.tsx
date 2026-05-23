"use client";

/**
 * components/FramesTab.tsx — 抽出済みフレームの表示・タグ編集タブ。
 *
 * ■ 機能:
 *   - サムネイルグリッド表示
 *   - タグのインライン編集
 *   - キャラクターフィルタ
 *   - フレームの削除 (→ rejected に移動)
 */

import { useEffect, useState, useCallback } from "react";
import { api, type FrameMeta, type Project } from "@/lib/api";
import { cn } from "@/lib/utils";

interface FramesTabProps {
  project: Project;
}

export function FramesTab({ project }: FramesTabProps) {
  const [frames, setFrames] = useState<FrameMeta[]>([]);
  const [filterChar, setFilterChar] = useState<string>("all");
  const [filterTag, setFilterTag] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editingFrame, setEditingFrame] = useState<FrameMeta | null>(null);
  const [editTags, setEditTags] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchFrames = useCallback(async () => {
    setLoading(true);
    try {
      const opts: { character_slug?: string; tag?: string } = {};
      if (filterChar !== "all") opts.character_slug = filterChar;
      if (filterTag) opts.tag = filterTag;
      const list = await api.listFrames(project.slug, opts);
      setFrames(list);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [project.slug, filterChar, filterTag]);

  useEffect(() => {
    fetchFrames();
  }, [fetchFrames]);

  const handleDelete = async (filename: string) => {
    await api.deleteFrame(project.slug, filename);
    setFrames((prev) => prev.filter((f) => f.filename !== filename));
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(filename);
      return next;
    });
  };

  const handleDeleteSelected = async () => {
    if (!confirm(`${selected.size} 枚を削除しますか？`)) return;
    for (const fn of selected) {
      await api.deleteFrame(project.slug, fn);
    }
    setFrames((prev) => prev.filter((f) => !selected.has(f.filename)));
    setSelected(new Set());
  };

  const openEdit = (frame: FrameMeta) => {
    setEditingFrame(frame);
    setEditTags(frame.tags.join(", "));
  };

  const handleSaveTags = async () => {
    if (!editingFrame) return;
    const newTags = editTags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const updated = await api.patchFrame(project.slug, editingFrame.filename, {
      tags: newTags,
    });
    setFrames((prev) =>
      prev.map((f) => (f.filename === updated.filename ? updated : f))
    );
    setEditingFrame(null);
  };

  const toggleSelect = (filename: string, e: React.MouseEvent) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (e.ctrlKey || e.metaKey) {
        next.has(filename) ? next.delete(filename) : next.add(filename);
      } else {
        next.clear();
        next.add(filename);
      }
      return next;
    });
  };

  return (
    <div className="space-y-4">
      {/* フィルターバー */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* キャラクターフィルター */}
        <div className="flex gap-1.5">
          <button
            onClick={() => setFilterChar("all")}
            className={cn(
              "rounded-full px-3 py-1 text-sm",
              filterChar === "all"
                ? "bg-accent text-white"
                : "bg-bg-surface border border-bg-border text-text-secondary"
            )}
          >
            全て
          </button>
          {project.characters.map((c) => (
            <button
              key={c.slug}
              onClick={() =>
                setFilterChar(filterChar === c.slug ? "all" : c.slug)
              }
              className={cn(
                "rounded-full px-3 py-1 text-sm",
                filterChar === c.slug
                  ? "bg-accent text-white"
                  : "bg-bg-surface border border-bg-border text-text-secondary hover:border-accent"
              )}
            >
              {c.name}
            </button>
          ))}
        </div>

        {/* タグ検索 */}
        <input
          className="rounded border border-bg-border bg-bg-surface px-3 py-1 text-sm placeholder-text-muted outline-none focus:border-accent"
          placeholder="タグで検索..."
          value={filterTag}
          onChange={(e) => setFilterTag(e.target.value)}
        />

        <div className="ml-auto flex items-center gap-2 text-sm text-text-secondary">
          <span>{frames.length} 枚</span>
          {selected.size > 0 && (
            <button
              onClick={handleDeleteSelected}
              className="rounded border border-red-800 px-3 py-1 text-red-400 hover:bg-red-900/20"
            >
              {selected.size} 枚を削除
            </button>
          )}
        </div>
      </div>

      {/* フレームグリッド */}
      {loading ? (
        <div className="text-center text-text-muted py-12">読み込み中...</div>
      ) : frames.length === 0 ? (
        <div className="text-center text-text-muted py-12">
          フレームがありません。Sources タブで抽出を実行してください。
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-3 lg:grid-cols-6 xl:grid-cols-8">
          {frames.map((frame) => (
            <div
              key={frame.filename}
              className={cn(
                "group relative cursor-pointer rounded-lg overflow-hidden border-2 transition-colors",
                selected.has(frame.filename)
                  ? "border-accent"
                  : "border-transparent hover:border-bg-border"
              )}
              onClick={(e) => toggleSelect(frame.filename, e)}
              onDoubleClick={() => openEdit(frame)}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/api/projects/${project.slug}/frames/${frame.filename}`}
                alt={frame.filename}
                className="aspect-square w-full object-cover"
                loading="lazy"
              />
              {/* ホバー時のアクションオーバーレイ */}
              <div className="absolute inset-0 hidden group-hover:flex flex-col justify-between p-1 bg-black/60">
                <div className="flex justify-end gap-1">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      openEdit(frame);
                    }}
                    className="rounded bg-bg-surface/80 px-1.5 py-0.5 text-xs hover:bg-accent"
                  >
                    編集
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(frame.filename);
                    }}
                    className="rounded bg-bg-surface/80 px-1.5 py-0.5 text-xs hover:bg-red-600"
                  >
                    ✕
                  </button>
                </div>
                {/* タグプレビュー */}
                <div className="text-xs text-white/80 truncate">
                  {frame.tags.slice(0, 3).join(", ")}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* タグ編集モーダル */}
      {editingFrame && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          onClick={() => setEditingFrame(null)}
        >
          <div
            className="w-[600px] rounded-xl bg-bg-surface border border-bg-border p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-semibold">{editingFrame.filename}</h3>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`/api/projects/${project.slug}/frames/${editingFrame.filename}`}
              alt=""
              className="w-full rounded max-h-64 object-contain bg-black"
            />
            <div>
              <label className="text-xs text-text-secondary mb-1 block">
                タグ (カンマ区切り)
              </label>
              <textarea
                className="w-full rounded bg-bg-raised border border-bg-border px-3 py-2 text-sm outline-none focus:border-accent h-20 resize-none"
                value={editTags}
                onChange={(e) => setEditTags(e.target.value)}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setEditingFrame(null)}
                className="rounded border border-bg-border px-4 py-2 text-sm hover:border-accent"
              >
                キャンセル
              </button>
              <button
                onClick={handleSaveTags}
                className="rounded bg-accent px-4 py-2 text-sm hover:bg-accent-hover"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
