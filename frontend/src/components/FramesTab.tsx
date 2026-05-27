"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type FrameMeta, type Project } from "@/lib/api";
import type { ProgressState } from "@/app/page";
import { cn } from "@/lib/utils";

interface FramesTabProps {
  project: Project;
  progress: Record<string, ProgressState>;
}

export function FramesTab({ project, progress }: FramesTabProps) {
  const [frames, setFrames] = useState<FrameMeta[]>([]);
  const [filterChar, setFilterChar] = useState<string>("all");
  const [filterTag, setFilterTag] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [editingFrame, setEditingFrame] = useState<FrameMeta | null>(null);
  const [editTags, setEditTags] = useState("");
  const [loading, setLoading] = useState(true);
  const [isTagging, setIsTagging] = useState(false);
  const [tagDone, setTagDone] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runningProgress = Object.values(progress).find(
    (p) => p.projectSlug === project.slug
  );
  const isRunning = isTagging || !!runningProgress;

  useEffect(() => () => { if (pollingRef.current) clearTimeout(pollingRef.current); }, []);

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

  useEffect(() => { fetchFrames(); }, [fetchFrames]);

  const toggleCheck = (filename: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      next.has(filename) ? next.delete(filename) : next.add(filename);
      return next;
    });
  };

  const allChecked = frames.length > 0 && frames.every((f) => checked.has(f.filename));
  const someChecked = frames.some((f) => checked.has(f.filename));

  const handleSelectAll = () => {
    setChecked(allChecked ? new Set() : new Set(frames.map((f) => f.filename)));
  };

  const handleSelectUntagged = () => {
    setChecked(new Set(frames.filter((f) => f.tags.length === 0).map((f) => f.filename)));
  };

  const handleTagSelected = async () => {
    if (checked.size === 0 || isRunning) return;
    if (pollingRef.current) clearTimeout(pollingRef.current);
    setTagDone(false);
    setIsTagging(true);

    let jobId: string;
    try {
      const res = await api.startTag(project.slug, { filenames: Array.from(checked), retag: true });
      jobId = res.job_id;
    } catch (err) {
      console.error(err);
      setIsTagging(false);
      return;
    }

    const poll = async () => {
      try {
        const job = await api.getJob(jobId);
        if (job.status === "done") {
          setIsTagging(false);
          setTagDone(true);
          await fetchFrames();
          setTimeout(() => setTagDone(false), 4000);
        } else if (job.status === "error") {
          setIsTagging(false);
        } else {
          pollingRef.current = setTimeout(poll, 600);
        }
      } catch {
        pollingRef.current = setTimeout(poll, 1000);
      }
    };
    pollingRef.current = setTimeout(poll, 300);
  };

  const handleDelete = async (filename: string) => {
    await api.deleteFrame(project.slug, filename);
    setFrames((prev) => prev.filter((f) => f.filename !== filename));
    setChecked((prev) => { const n = new Set(prev); n.delete(filename); return n; });
  };

  const openEdit = (frame: FrameMeta) => {
    setEditingFrame(frame);
    setEditTags(frame.tags.join(", "));
  };

  const handleSaveTags = async () => {
    if (!editingFrame) return;
    const newTags = editTags.split(",").map((t) => t.trim()).filter(Boolean);
    const updated = await api.patchFrame(project.slug, editingFrame.filename, { tags: newTags });
    setFrames((prev) => prev.map((f) => (f.filename === updated.filename ? updated : f)));
    setEditingFrame(null);
  };

  return (
    <div className="flex flex-col h-full -m-4">
      {/* 上部固定バー */}
      <div className="sticky top-0 z-20 bg-bg-base/95 backdrop-blur border-b border-bg-border px-4 py-2.5 flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-1.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={allChecked}
            ref={(el) => { if (el) el.indeterminate = someChecked && !allChecked; }}
            onChange={handleSelectAll}
            className="accent-accent w-3.5 h-3.5"
          />
          <span className="text-xs text-text-secondary">全選択</span>
        </label>

        <button
          onClick={handleSelectUntagged}
          className="text-xs text-text-muted hover:text-text-secondary border border-bg-border rounded px-2 py-0.5 hover:border-accent transition-colors"
        >
          未タグのみ
        </button>

        <span className="text-xs text-text-muted">
          {checked.size > 0 ? `${checked.size} 枚選択中 / ${frames.length} 枚` : `${frames.length} 枚`}
        </span>

        <div className="flex-1" />

        {(isRunning || tagDone) ? (
          <div className={cn(
            "flex items-center gap-2 rounded px-3 py-1.5 text-xs font-medium border",
            isRunning ? "bg-accent/10 border-accent text-accent-light animate-pulse" : "bg-green-900/30 border-green-700 text-green-400"
          )}>
            {isRunning && (
              <svg className="h-3 w-3 animate-spin shrink-0" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
              </svg>
            )}
            {isRunning
              ? (runningProgress ? `${runningProgress.stage}　${runningProgress.current}/${runningProgress.total} 枚` : "タグ付け中...")
              : "✓ タグ付け完了"}
          </div>
        ) : (
          <button
            onClick={handleTagSelected}
            disabled={checked.size === 0}
            className={cn(
              "rounded px-3 py-1.5 text-xs font-medium transition-all duration-150",
              checked.size === 0 ? "bg-bg-border text-text-muted cursor-not-allowed" : "bg-accent hover:bg-accent-hover active:scale-95"
            )}
          >
            {checked.size > 0 ? `選択した ${checked.size} 枚を WD14 タグ付け` : "画像を選択してください"}
          </button>
        )}

        {checked.size > 0 && !isRunning && (
          <button
            onClick={async () => {
              if (!confirm(`${checked.size} 枚を削除しますか？`)) return;
              for (const fn of checked) await api.deleteFrame(project.slug, fn);
              setFrames((prev) => prev.filter((f) => !checked.has(f.filename)));
              setChecked(new Set());
            }}
            className="rounded border border-red-800 px-3 py-1.5 text-xs text-red-400 hover:bg-red-900/20 transition-colors"
          >
            {checked.size} 枚を削除
          </button>
        )}
      </div>

      {/* フィルターバー */}
      <div className="px-4 py-2 flex items-center gap-2 flex-wrap border-b border-bg-border">
        <div className="flex gap-1.5">
          <button onClick={() => setFilterChar("all")}
            className={cn("rounded-full px-3 py-0.5 text-xs", filterChar === "all" ? "bg-accent text-white" : "bg-bg-surface border border-bg-border text-text-secondary")}
          >全て</button>
          {project.characters.map((c) => (
            <button key={c.slug} onClick={() => setFilterChar(filterChar === c.slug ? "all" : c.slug)}
              className={cn("rounded-full px-3 py-0.5 text-xs", filterChar === c.slug ? "bg-accent text-white" : "bg-bg-surface border border-bg-border text-text-secondary hover:border-accent")}
            >{c.name}</button>
          ))}
        </div>
        <input
          className="rounded border border-bg-border bg-bg-surface px-3 py-0.5 text-xs placeholder-text-muted outline-none focus:border-accent"
          placeholder="タグで検索..."
          value={filterTag}
          onChange={(e) => setFilterTag(e.target.value)}
        />
      </div>

      {/* グリッド */}
      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <div className="text-center text-text-muted py-12">読み込み中...</div>
        ) : frames.length === 0 ? (
          <div className="text-center text-text-muted py-12">
            フレームがありません。Upload タブで画像をアップロードしてください。
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-3 lg:grid-cols-6 xl:grid-cols-8">
            {frames.map((frame) => {
              const isChecked = checked.has(frame.filename);
              const isTagged = frame.tags.length > 0;
              return (
                <div
                  key={frame.filename}
                  className={cn(
                    "group relative rounded-lg overflow-hidden border-2 transition-all duration-150 cursor-pointer",
                    isChecked ? "border-accent shadow-[0_0_8px_1px_rgba(124,58,237,0.4)]" : "border-transparent hover:border-bg-border"
                  )}
                  onClick={() => toggleCheck(frame.filename)}
                  onDoubleClick={(e) => { e.stopPropagation(); openEdit(frame); }}
                >
                  {/* チェックボックス (左上) */}
                  <div className="absolute top-1 left-1 z-10" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleCheck(frame.filename)}
                      className="accent-accent w-3.5 h-3.5 cursor-pointer"
                    />
                  </div>

                  {/* タグステータスバッジ (右上) */}
                  <div className="absolute top-1 right-1 z-10">
                    {isTagged
                      ? <span className="rounded bg-green-900/80 px-1 py-0.5 text-[10px] font-bold text-green-400 leading-none">✓</span>
                      : <span className="rounded bg-yellow-900/80 px-1 py-0.5 text-[10px] font-bold text-yellow-400 leading-none">△</span>
                    }
                  </div>

                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`/api/projects/${project.slug}/frames/${frame.filename}`}
                    alt={frame.filename}
                    className="aspect-square w-full object-cover"
                    loading="lazy"
                  />

                  <div className="absolute inset-0 hidden group-hover:flex flex-col justify-between p-1 bg-black/60">
                    <div className="flex justify-end gap-1 mt-4">
                      <button onClick={(e) => { e.stopPropagation(); openEdit(frame); }}
                        className="rounded bg-bg-surface/80 px-1.5 py-0.5 text-xs hover:bg-accent">編集</button>
                      <button onClick={(e) => { e.stopPropagation(); handleDelete(frame.filename); }}
                        className="rounded bg-bg-surface/80 px-1.5 py-0.5 text-xs hover:bg-red-600">✕</button>
                    </div>
                    <div className="text-xs text-white/80 truncate">
                      {frame.tags.slice(0, 3).join(", ")}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* タグ編集モーダル */}
      {editingFrame && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={() => setEditingFrame(null)}>
          <div className="w-[600px] rounded-xl bg-bg-surface border border-bg-border p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold">{editingFrame.filename}</h3>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`/api/projects/${project.slug}/frames/${editingFrame.filename}`} alt=""
              className="w-full rounded max-h-64 object-contain bg-black" />
            <div>
              <label className="text-xs text-text-secondary mb-1 block">タグ (カンマ区切り)</label>
              <textarea
                className="w-full rounded bg-bg-raised border border-bg-border px-3 py-2 text-sm outline-none focus:border-accent h-20 resize-none"
                value={editTags}
                onChange={(e) => setEditTags(e.target.value)}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setEditingFrame(null)} className="rounded border border-bg-border px-4 py-2 text-sm hover:border-accent">キャンセル</button>
              <button onClick={handleSaveTags} className="rounded bg-accent px-4 py-2 text-sm hover:bg-accent-hover">保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
