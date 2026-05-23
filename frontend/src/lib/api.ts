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
  source_count: number;
  llm_enabled: boolean;
}

export interface Source {
  idx: number;
  path: string;
  added_at: string;
  excluded_refs: Record<string, string[]>;
  extraction_runs: unknown[];
  segments: { start_seconds: number; end_seconds: number; label: string }[];
  duration_seconds: number | null;
  fps: number | null;
}

export interface FrameMeta {
  filename: string;
  character_slug: string;
  track_id: number;
  frame_idx: number;
  source_idx: number;
  video_stem: string;
  tags: string[];
  caption?: string;
  rating?: string;
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
export interface SceneConfig   { threshold: number; min_scene_len_frames: number }
export interface DetectConfig  { person_score_min: number; face_score_min: number; frame_stride: number; detect_faces: boolean }
export interface TrackConfig   { track_thresh: number; match_thresh: number; frame_rate: number; track_buffer: number; min_tracklet_len: number }
export interface IdentifyConfig { body_max_distance_strict: number; body_max_distance_loose: number; sample_frames_per_tracklet: number }
export interface FrameSelectConfig { short_tracklet_seconds: number; long_tracklet_seconds: number; top_k_short: number; top_k_long: number; candidate_cap: number; dedup_min_frame_gap: number }
export interface CropConfig    { longest_side: number; pad_ratio: number }
export interface TagConfig     { model_name: string; general_threshold: number; character_threshold: number; no_underline: boolean; drop_overlap: boolean; vram_flush_every: number }
export interface DedupConfig   { max_distance: number; window_size: number }

export interface Thresholds {
  scene:        SceneConfig;
  detect:       DetectConfig;
  track:        TrackConfig;
  identify:     IdentifyConfig;
  frame_select: FrameSelectConfig;
  crop:         CropConfig;
  tag:          TagConfig;
  dedup:        DedupConfig;
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

  // --- Sources ---
  listSources: (slug: string) =>
    request<Source[]>(`/projects/${slug}/sources`),
  addSource: (slug: string, path: string) =>
    request<Source>(`/projects/${slug}/sources`, {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  removeSource: (slug: string, idx: number) =>
    request<void>(`/projects/${slug}/sources/${idx}`, { method: "DELETE" }),
  updateSegments: (
    slug: string,
    idx: number,
    segments: Source["segments"]
  ) =>
    request(`/projects/${slug}/sources/${idx}/segments`, {
      method: "PATCH",
      body: JSON.stringify({ segments }),
    }),

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

  // --- Refs ---
  listRefs: (slug: string, charSlug: string) =>
    request<{ path: string; added_at: string }[]>(
      `/projects/${slug}/characters/${charSlug}/refs`
    ),
  uploadRef: async (slug: string, charSlug: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(
      `${BASE}/projects/${slug}/characters/${charSlug}/refs`,
      { method: "POST", body: form }
    );
    if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
    return res.json();
  },
  deleteRef: (slug: string, refFilename: string) =>
    request<void>(`/projects/${slug}/refs/${refFilename}`, {
      method: "DELETE",
    }),

  // --- Frames ---
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
  startExtract: (slug: string, sourceIdx: number) =>
    request<{ job_id: string }>(`/projects/${slug}/extract`, {
      method: "POST",
      body: JSON.stringify({ source_idx: sourceIdx }),
    }),
  startRerun: (slug: string, sourceIdx: number) =>
    request<{ job_id: string }>(`/projects/${slug}/rerun`, {
      method: "POST",
      body: JSON.stringify({ source_idx: sourceIdx }),
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
