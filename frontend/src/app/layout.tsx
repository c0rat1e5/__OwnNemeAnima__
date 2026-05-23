import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Neme-Anima",
  description: "アニメキャラクター LoRA ビルダー",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja" className="dark">
      <body className="min-h-screen bg-bg-base text-text-primary antialiased">
        {children}
      </body>
    </html>
  );
}
