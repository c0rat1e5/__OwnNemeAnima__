import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind クラスを安全にマージするユーティリティ。 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** ファイルパスからファイル名だけ取り出す。 */
export function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

/** 秒数を "HH:MM:SS" 形式にフォーマットする。 */
export function formatSeconds(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}
