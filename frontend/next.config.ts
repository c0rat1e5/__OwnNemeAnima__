import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Python バックエンド (FastAPI) へのプロキシ設定
  // 開発時: localhost:8000 にリダイレクト
  // 本番: Next.js は静的エクスポートして FastAPI が配信する
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
  // 画像最適化を無効化 (静的エクスポート時に必要)
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
