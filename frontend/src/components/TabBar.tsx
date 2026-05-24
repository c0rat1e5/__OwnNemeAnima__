"use client";

/**
 * components/TabBar.tsx — Sources / Frames / Training / Settings タブ。
 */

import { cn } from "@/lib/utils";

export type TabId = "upload" | "frames" | "training" | "settings";

const TABS: { id: TabId; label: string }[] = [
  { id: "upload",   label: "Upload"   },
  { id: "frames",   label: "Frames"   },
  { id: "training", label: "Training" },
  { id: "settings", label: "Settings" },
];

interface TabBarProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
}

export function TabBar({ activeTab, onTabChange }: TabBarProps) {
  return (
    <div className="flex border-b border-bg-border bg-bg-surface">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={cn(
            "px-6 py-3 text-sm font-medium transition-colors",
            activeTab === tab.id
              ? "border-b-2 border-accent text-accent"
              : "text-text-secondary hover:text-text-primary"
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
