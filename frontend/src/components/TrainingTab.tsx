"use client";

/**
 * components/TrainingTab.tsx — LoRA 学習設定・実行タブ。
 */

import { useEffect, useState, useCallback } from "react";
import { api, type TrainingConfig, type Project } from "@/lib/api";

interface TrainingTabProps {
  project: Project;
}

const FIELD_LABELS: Partial<Record<keyof TrainingConfig, string>> = {
  diffusion_pipe_dir:       "diffusion-pipe ディレクトリ",
  anima_dit_path:           "Anima DiT チェックポイント",
  qwen_vae_path:            "Qwen VAE パス",
  qwen_text_encoder_path:   "Qwen テキストエンコーダーパス",
  rank:                     "LoRA ランク",
  alpha:                    "LoRA alpha",
  lr:                       "学習率",
  epochs:                   "エポック数",
  batch_size:               "バッチサイズ",
  save_every_n_epochs:      "N エポックごとに保存",
  keep_last_n_checkpoints:  "最新 N チェックポイントを保持 (0=全部)",
  trigger_token:            "トリガーワード",
  core_tag_pruning_enabled: "コアタグ除外を有効化",
  core_tag_threshold:       "コアタグ判定閾値",
};

export function TrainingTab({ project }: TrainingTabProps) {
  const [configs, setConfigs] = useState<Record<string, TrainingConfig>>({});
  const [activeChar, setActiveChar] = useState(
    project.characters[0]?.slug ?? "default"
  );
  const [status, setStatus] = useState<{
    running: boolean;
    job_id: string | null;
  }>({ running: false, job_id: null });
  const [trainingLog, setTrainingLog] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const fetchConfig = useCallback(async () => {
    const cfg = await api.getTrainingConfig(project.slug);
    setConfigs(cfg);
  }, [project.slug]);

  const fetchStatus = useCallback(async () => {
    const s = await api.getTrainingStatus(project.slug);
    setStatus(s);
  }, [project.slug]);

  useEffect(() => {
    fetchConfig();
    fetchStatus();
  }, [fetchConfig, fetchStatus]);

  const cfg = configs[activeChar] as TrainingConfig | undefined;

  const handleChange = <K extends keyof TrainingConfig>(
    key: K,
    value: TrainingConfig[K]
  ) => {
    if (!cfg) return;
    setConfigs((prev) => ({
      ...prev,
      [activeChar]: { ...prev[activeChar], [key]: value },
    }));
  };

  const handleSave = async () => {
    if (!cfg) return;
    setSaving(true);
    try {
      await api.patchTrainingConfig(project.slug, {
        ...cfg,
        character_slug: activeChar,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleStart = async () => {
    await handleSave();
    await api.startTraining(project.slug, activeChar);
    fetchStatus();
    setTrainingLog([]);
  };

  const handleStop = async () => {
    await api.stopTraining(project.slug);
    fetchStatus();
  };

  if (!cfg) {
    return <div className="text-text-muted">設定を読み込み中...</div>;
  }

  return (
    <div className="max-w-2xl space-y-6">
      {/* キャラクター選択 */}
      {project.characters.length > 1 && (
        <div className="flex gap-2">
          {project.characters.map((c) => (
            <button
              key={c.slug}
              onClick={() => setActiveChar(c.slug)}
              className={`rounded-full px-3 py-1 text-sm ${
                activeChar === c.slug
                  ? "bg-accent text-white"
                  : "bg-bg-surface border border-bg-border text-text-secondary"
              }`}
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

      {/* 実行ステータス */}
      <div className={`rounded-lg border p-4 ${
        status.running
          ? "border-accent/50 bg-accent/10"
          : "border-bg-border bg-bg-surface"
      }`}>
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">
              {status.running ? "学習実行中" : "待機中"}
            </div>
            {status.job_id && (
              <div className="text-xs text-text-muted mt-0.5">
                Job: {status.job_id}
              </div>
            )}
          </div>
          <div className="flex gap-2">
            {status.running ? (
              <button
                onClick={handleStop}
                className="rounded bg-red-700 px-4 py-2 text-sm hover:bg-red-600"
              >
                停止
              </button>
            ) : (
              <button
                onClick={handleStart}
                className="rounded bg-accent px-4 py-2 text-sm hover:bg-accent-hover"
              >
                学習開始
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 設定フォーム */}
      <div className="space-y-4">
        <h3 className="font-semibold text-text-primary">パス設定</h3>
        {(
          [
            "diffusion_pipe_dir",
            "anima_dit_path",
            "qwen_vae_path",
            "qwen_text_encoder_path",
          ] as const
        ).map((key) => (
          <div key={key}>
            <label className="block text-xs text-text-secondary mb-1">
              {FIELD_LABELS[key]}
            </label>
            <input
              className="w-full rounded border border-bg-border bg-bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
              value={String(cfg[key])}
              onChange={(e) =>
                handleChange(key, e.target.value as TrainingConfig[typeof key])
              }
            />
          </div>
        ))}

        <h3 className="font-semibold text-text-primary pt-2">ハイパーパラメータ</h3>
        <div className="grid grid-cols-2 gap-3">
          {(
            [
              "rank", "alpha", "lr", "epochs",
              "batch_size", "save_every_n_epochs",
              "keep_last_n_checkpoints",
            ] as const
          ).map((key) => (
            <div key={key}>
              <label className="block text-xs text-text-secondary mb-1">
                {FIELD_LABELS[key]}
              </label>
              <input
                type="number"
                step={key === "lr" ? "0.00001" : "1"}
                className="w-full rounded border border-bg-border bg-bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
                value={Number(cfg[key])}
                onChange={(e) =>
                  handleChange(
                    key,
                    (key === "lr" || key === "alpha"
                      ? parseFloat(e.target.value)
                      : parseInt(e.target.value)) as TrainingConfig[typeof key]
                  )
                }
              />
            </div>
          ))}
        </div>

        <div>
          <label className="block text-xs text-text-secondary mb-1">
            {FIELD_LABELS["trigger_token"]}
          </label>
          <input
            className="w-full rounded border border-bg-border bg-bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
            value={cfg.trigger_token}
            onChange={(e) => handleChange("trigger_token", e.target.value)}
          />
        </div>
      </div>

      {/* 保存ボタン */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="rounded bg-accent px-6 py-2 text-sm font-medium hover:bg-accent-hover disabled:opacity-50"
      >
        {saving ? "保存中..." : "設定を保存"}
      </button>

      {/* 学習ログ */}
      {trainingLog.length > 0 && (
        <div>
          <h3 className="font-semibold mb-2">学習ログ</h3>
          <div className="h-48 overflow-y-auto rounded bg-black p-3 font-mono text-xs text-green-400">
            {trainingLog.map((line, i) => (
              <div key={i}>{line}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
