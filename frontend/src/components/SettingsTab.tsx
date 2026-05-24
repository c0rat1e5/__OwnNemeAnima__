"use client";

/**
 * components/SettingsTab.tsx — プロジェクト設定タブ。
 *
 * ■ 機能:
 *   1. 閾値 (Thresholds) の表示・編集
 *      - Scene / Detect / Track / Identify / FrameSelect / Crop / Tag / Dedup
 *   2. LLM キャプション設定 (OpenAI 互換 API)
 *   3. 保存 / リセット
 *
 * ■ 設計メモ:
 *   - 閾値は thresholds.json に保存される (project.json とは別ファイル)
 *   - LLM 設定は project.json に保存される
 *   - PATCH /api/projects/{slug}/settings で一括更新
 */

import { useEffect, useState, useCallback } from "react";
import {
  api,
  type ProjectSettings,
  type Thresholds,
  type LLMConfig,
  type Project,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface SettingsTabProps {
  project: Project;
  onRefresh: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// 小さな入力コンポーネント
// ─────────────────────────────────────────────────────────────────────────────

function FieldRow({
  label,
  tooltip,
  children,
}: {
  label: string;
  tooltip?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-4 py-2">
      <label
        className="w-52 shrink-0 text-sm text-text-secondary pt-1"
        title={tooltip}
      >
        {label}
        {tooltip && (
          <span className="ml-1 text-text-muted cursor-help text-xs">(?)</span>
        )}
      </label>
      <div className="flex-1">{children}</div>
    </div>
  );
}

function NumberInput({
  value,
  onChange,
  step = 1,
  min,
  max,
}: {
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
}) {
  return (
    <input
      type="number"
      value={value}
      step={step}
      min={min}
      max={max}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-32 rounded border border-bg-border bg-bg-raised px-2 py-1 text-sm text-text-primary focus:border-accent focus:outline-none"
    />
  );
}

function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-10 items-center rounded-full transition-colors",
        checked ? "bg-accent" : "bg-bg-border"
      )}
    >
      <span
        className={cn(
          "inline-block h-4 w-4 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-5" : "translate-x-1"
        )}
      />
    </button>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: "text" | "password" | "url";
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full rounded border border-bg-border bg-bg-raised px-2 py-1 text-sm text-text-primary focus:border-accent focus:outline-none"
    />
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-bg-border bg-bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold text-accent uppercase tracking-wide">
        {title}
      </h3>
      <div className="divide-y divide-bg-border">{children}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// メインコンポーネント
// ─────────────────────────────────────────────────────────────────────────────

export function SettingsTab({ project, onRefresh }: SettingsTabProps) {
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── 読み込み ─────────────────────────────────────────────────────────────
  const fetchSettings = useCallback(async () => {
    try {
      const s = await api.getSettings(project.slug);
      setSettings(s);
      setDirty(false);
    } catch (err) {
      setError(String(err));
    }
  }, [project.slug]);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  // ── 更新ヘルパー ──────────────────────────────────────────────────────────

  function setThresh<S extends keyof Thresholds, K extends keyof Thresholds[S]>(
    section: S,
    key: K,
    value: Thresholds[S][K]
  ) {
    setSettings((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        thresholds: {
          ...prev.thresholds,
          [section]: {
            ...prev.thresholds[section],
            [key]: value,
          },
        },
      };
    });
    setDirty(true);
  }

  function setLLM<K extends keyof LLMConfig>(key: K, value: LLMConfig[K]) {
    setSettings((prev) => {
      if (!prev) return prev;
      return { ...prev, llm: { ...prev.llm, [key]: value } };
    });
    setDirty(true);
  }

  // ── 保存 ─────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      await api.patchSettings(project.slug, {
        thresholds: settings.thresholds as unknown as Partial<Record<keyof Thresholds, unknown>>,
        llm: settings.llm,
      });
      setDirty(false);
      onRefresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  // ── リセット ──────────────────────────────────────────────────────────────
  const handleReset = () => {
    fetchSettings();
  };

  // ─────────────────────────────────────────────────────────────────────────
  if (!settings) {
    return (
      <div className="flex h-32 items-center justify-center text-text-secondary text-sm">
        {error ? `エラー: ${error}` : "読み込み中..."}
      </div>
    );
  }

  const t = settings.thresholds;
  const llm = settings.llm;

  return (
    <div className="flex flex-col gap-4 max-w-3xl">

      {/* ── エラー通知 ── */}
      {error && (
        <div className="rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* ① クロップ */}
      <Section title="① Crop">
        <FieldRow
          label="longest_side (px)"
          tooltip="画像の長辺をこの px にリサイズする (デフォルト 1024)。"
        >
          <NumberInput
            value={t.crop.longest_side}
            onChange={(v) => setThresh("crop", "longest_side", v)}
            step={64}
            min={256}
            max={2048}
          />
        </FieldRow>
        <FieldRow
          label="pad_ratio"
          tooltip="bbox に対して何割のパディングを加えるか (0.10 = 10%)。"
        >
          <NumberInput
            value={t.crop.pad_ratio}
            onChange={(v) => setThresh("crop", "pad_ratio", v)}
            step={0.01}
            min={0}
            max={1}
          />
        </FieldRow>
      </Section>

      {/* ② WD14 タグ付け */}
      <Section title="② Tagging (WD14)">
        <FieldRow
          label="general_threshold"
          tooltip="一般タグの信頼スコア下限。高いほどタグが絞られる。"
        >
          <NumberInput
            value={t.tag.general_threshold}
            onChange={(v) => setThresh("tag", "general_threshold", v)}
            step={0.05}
            min={0}
            max={1}
          />
        </FieldRow>
        <FieldRow
          label="character_threshold"
          tooltip="キャラクタータグの信頼スコア下限。"
        >
          <NumberInput
            value={t.tag.character_threshold}
            onChange={(v) => setThresh("tag", "character_threshold", v)}
            step={0.05}
            min={0}
            max={1}
          />
        </FieldRow>
        <FieldRow
          label="no_underline"
          tooltip="アンダースコア (_) をスペースに変換する。"
        >
          <Toggle
            checked={t.tag.no_underline}
            onChange={(v) => setThresh("tag", "no_underline", v)}
          />
        </FieldRow>
      </Section>

      {/* ③ 重複除去 */}
      <Section title="③ Deduplication (CCIP)">
        <FieldRow
          label="max_distance"
          tooltip="この距離以下のペアを『重複』と判定して reject する。"
        >
          <NumberInput
            value={t.dedup.max_distance}
            onChange={(v) => setThresh("dedup", "max_distance", v)}
            step={0.01}
            min={0}
            max={1}
          />
        </FieldRow>
      </Section>

      {/* LLM キャプション */}
      <Section title="LLM Caption (OpenAI-compatible)">
        <FieldRow
          label="enabled"
          tooltip="WD14 タグに加えて LLM で自然言語キャプションを生成する。"
        >
          <Toggle checked={llm.enabled} onChange={(v) => setLLM("enabled", v)} />
        </FieldRow>
        <FieldRow
          label="endpoint"
          tooltip="OpenAI 互換 API のベース URL (例: http://localhost:1234)。"
        >
          <TextInput
            value={llm.endpoint}
            onChange={(v) => setLLM("endpoint", v)}
            placeholder="http://localhost:1234"
            type="url"
          />
        </FieldRow>
        <FieldRow label="model">
          <TextInput
            value={llm.model}
            onChange={(v) => setLLM("model", v)}
            placeholder="model-name"
          />
        </FieldRow>
        <FieldRow
          label="api_key"
          tooltip="Bearer トークン。LM Studio などトークン不要の場合は空欄。"
        >
          <TextInput
            value={llm.api_key}
            onChange={(v) => setLLM("api_key", v)}
            type="password"
            placeholder="(空欄 = トークンなし)"
          />
        </FieldRow>
        <FieldRow
          label="prompt"
          tooltip="キャプション生成プロンプト。空欄はデフォルトプロンプトを使用。"
        >
          <textarea
            value={llm.prompt}
            onChange={(e) => setLLM("prompt", e.target.value)}
            rows={3}
            placeholder="(空欄 = デフォルトプロンプト)"
            className="w-full rounded border border-bg-border bg-bg-raised px-2 py-1 text-sm text-text-primary focus:border-accent focus:outline-none resize-y"
          />
        </FieldRow>
      </Section>

      {/* 保存 / リセットボタン */}
      <div className="flex items-center gap-3 pb-4">
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          className={cn(
            "rounded px-4 py-2 text-sm font-medium transition-colors",
            dirty && !saving
              ? "bg-accent text-white hover:bg-accent-hover"
              : "bg-bg-border text-text-muted cursor-not-allowed"
          )}
        >
          {saving ? "保存中..." : "保存"}
        </button>
        <button
          onClick={handleReset}
          disabled={!dirty || saving}
          className="rounded px-4 py-2 text-sm text-text-secondary hover:text-text-primary transition-colors disabled:text-text-muted disabled:cursor-not-allowed"
        >
          リセット
        </button>
        {dirty && !saving && (
          <span className="text-xs text-text-muted">未保存の変更があります</span>
        )}
      </div>

      {/* プロジェクト情報 */}
      <div className="rounded-lg border border-bg-border bg-bg-surface p-4 text-xs text-text-muted">
        <p><span className="text-text-secondary">slug:</span> {project.slug}</p>
        <p><span className="text-text-secondary">root:</span> {project.root}</p>
        <p><span className="text-text-secondary">created:</span> {new Date(project.created_at).toLocaleString("ja-JP")}</p>
        <p className="mt-1 text-text-muted">
          閾値は <code className="text-accent">{project.root}/thresholds.json</code> に保存されます。
          LLM 設定は <code className="text-accent">project.json</code> に保存されます。
        </p>
      </div>

    </div>
  );
}
