/**
 * lib/api.ts — バックエンド API との通信レイヤー。
 *
 * fetch の薄いラッパーで、全エンドポイントをここに集約する。
 * エラーは Error をスローするので呼び出し元で try/catch する。
 */

const BASE = "/api";

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ─────────────────────────────────────────────
// 型定義
// ─────────────────────────────────────────────

export interface Character {
  slug: string;
  name: string;
  trigger_token: string;
  ref_count: number;
}

export interface Project {
  slug: string;
  name: string;
  root: string;
  created_at: string;
  characters: Character[];
  llm_enabled: boolean;
}

export interface FrameMeta {
  filename: string;
  character_slug: string;
  tags: string[];
  caption?: string;
  added_at?: string;
}

export interface Job {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  status: "queued" | "running" | "done" | "error";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface TrainingConfig {
  preset: string;
  diffusion_pipe_dir: string;
  anima_dit_path: string;
  qwen_vae_path: string;
  qwen_text_encoder_path: string;
  rank: number;
  alpha: number;
  lr: number;
  epochs: number;
  batch_size: number;
  save_every_n_epochs: number;
  keep_last_n_checkpoints: number;
  trigger_token: string;
  core_tag_pruning_enabled: boolean;
  core_tag_threshold: number;
  repeat_multiplier: number;
}

// ─── 閾値 (Thresholds) ────────────────────────────────────────────────────────
export interface CropConfig  { longest_side: number; pad_ratio: number }
export interface TagConfig   { model_name: string; general_threshold: number; character_threshold: number; no_underline: boolean; drop_overlap: boolean; vram_flush_every: number }
export interface DedupConfig { max_distance: number; embed_batch_size: number }

export interface Thresholds {
  crop:  CropConfig;
  tag:   TagConfig;
  dedup: DedupConfig;
}

export interface LLMConfig {
  enabled:  boolean;
  endpoint: string;
  model:    string;
  prompt:   string;
  api_key:  string;
}

export interface ProjectSettings {
  thresholds: Thresholds;
  llm:        LLMConfig;
}

// ─────────────────────────────────────────────
// プロジェクト API
// ─────────────────────────────────────────────

export const api = {
  // --- Projects ---
  listProjects: () => request<Project[]>("/projects"),
  createProject: (root: string, name: string) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify({ root, name }),
    }),
  getProject: (slug: string) => request<Project>(`/projects/${slug}`),
  deleteProject: (slug: string) =>
    request<void>(`/projects/${slug}`, { method: "DELETE" }),

  // --- Characters ---
  addCharacter: (slug: string, name: string) =>
    request<Character>(`/projects/${slug}/characters`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  removeCharacter: (slug: string, charSlug: string) =>
    request<void>(`/projects/${slug}/characters/${charSlug}`, {
      method: "DELETE",
    }),

  // --- Frames アップロード ---
  uploadFrames: async (
    slug: string,
    files: File[],
    characterSlug?: string
  ): Promise<FrameMeta[]> => {
    const results: FrameMeta[] = [];
    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      const url = characterSlug
        ? `${BASE}/projects/${slug}/frames?character_slug=${encodeURIComponent(characterSlug)}`
        : `${BASE}/projects/${slug}/frames`;
      const res = await fetch(url, { method: "POST", body: form });
      if (!res.ok) throw new Error(`Upload failed for ${file.name}: ${res.statusText}`);
      results.push(await res.json());
    }
    return results;
  },

  // --- Frames 一覧 ---
  listFrames: (
    slug: string,
    opts?: { character_slug?: string; tag?: string }
  ) => {
    const params = new URLSearchParams();
    if (opts?.character_slug) params.set("character_slug", opts.character_slug);
    if (opts?.tag) params.set("tag", opts.tag);
    return request<FrameMeta[]>(
      `/projects/${slug}/frames${params.size ? `?${params}` : ""}`
    );
  },
  patchFrame: (
    slug: string,
    filename: string,
    patch: { tags?: string[]; caption?: string; character_slug?: string }
  ) =>
    request<FrameMeta>(`/projects/${slug}/frames/${filename}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteFrame: (slug: string, filename: string) =>
    request<void>(`/projects/${slug}/frames/${filename}`, {
      method: "DELETE",
    }),

  // --- Queue ---
  startTag: (slug: string, opts?: { character_slug?: string; retag?: boolean }) =>
    request<{ job_id: string }>(`/projects/${slug}/tag`, {
      method: "POST",
      body: JSON.stringify(opts ?? {}),
    }),
  listJobs: () => request<Job[]>("/jobs"),
  getJob: (jobId: string) => request<Job>(`/jobs/${jobId}`),

  // --- Training ---
  getTrainingConfig: (slug: string) =>
    request<Record<string, TrainingConfig>>(`/projects/${slug}/training/config`),
  patchTrainingConfig: (
    slug: string,
    patch: Partial<TrainingConfig> & { character_slug?: string }
  ) =>
    request<TrainingConfig>(`/projects/${slug}/training/config`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  startTraining: (slug: string, charSlug?: string) =>
    request<{ job_id: string }>(`/projects/${slug}/training/start`, {
      method: "POST",
      body: JSON.stringify({ character_slug: charSlug }),
    }),
  stopTraining: (slug: string) =>
    request<{ ok: boolean }>(`/projects/${slug}/training/stop`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  getTrainingStatus: (slug: string) =>
    request<{ running: boolean; job_id: string | null }>(
      `/projects/${slug}/training/status`
    ),
  getCoreTags: (slug: string, charSlug: string) =>
    request<{
      core_tags: { tag: string; ratio: number }[];
      threshold: number;
      total_frames: number;
    }>(`/projects/${slug}/training/core-tags/${charSlug}`),

  // --- Settings (閾値 + LLM) ---
  getSettings: (slug: string) =>
    request<ProjectSettings>(`/projects/${slug}/settings`),
  patchSettings: (
    slug: string,
    patch: { thresholds?: Partial<Record<keyof Thresholds, unknown>>; llm?: Partial<LLMConfig> }
  ) =>
    request<ProjectSettings>(`/projects/${slug}/settings`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
};

// ─────────────────────────────────────────────
// SSE フック (イベントストリーム)
// ─────────────────────────────────────────────

export type SSEEvent = {
  type: string;
  data: Record<string, unknown>;
};

/**
 * /api/events に接続して SSE イベントを受け取るコールバック登録。
 * 返値の cleanup 関数でイベントソースを閉じる。
 */
export function connectSSE(
  onEvent: (e: SSEEvent) => void
): () => void {
  const es = new EventSource("/api/events");

  const handler = (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      onEvent({ type: e.type || "message", data });
    } catch {
      // ignore parse errors
    }
  };

  // 各イベント種別を個別にリッスン
  const eventTypes = [
    "connected",
    "job_queued",
    "progress",
    "job_done",
    "job_error",
    "training_start",
    "training_log",
    "training_done",
  ];
  for (const type of eventTypes) {
    es.addEventListener(type, handler as EventListener);
  }

  return () => es.close();
}
