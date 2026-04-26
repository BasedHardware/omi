import { Navigate, useLocation } from "react-router-dom";
import { AudioLines, Brain, Rewind, AudioWaveform } from "lucide-react";
import { ConversationsPage } from "../conversations/ConversationsPage";
import { MemoriesPage } from "../memories/MemoriesPage";
import { AuraPage } from "../aura/AuraPage";
import { WhisprPage } from "../whispr/WhisprPage";
import { SectionTabBar, type SectionTabDef } from "./SectionTabBar";

type LibraryTab = "meetings" | "memories" | "rewind" | "whispr";

const TABS: SectionTabDef<LibraryTab>[] = [
  { id: "meetings", label: "Meetings", icon: AudioLines, path: "/library/meetings" },
  { id: "memories", label: "Memories", icon: Brain, path: "/library/memories" },
  { id: "rewind", label: "Rewind", icon: Rewind, path: "/library/rewind" },
  { id: "whispr", label: "Whispr", icon: AudioWaveform, path: "/library/whispr" },
];

const DEFAULT_TAB: LibraryTab = "meetings";

export function LibraryPage() {
  const { pathname } = useLocation();

  if (pathname === "/library" || pathname === "/library/") {
    return <Navigate to={`/library/${DEFAULT_TAB}`} replace />;
  }

  const tab = TABS.find((t) => pathname.startsWith(t.path))?.id ?? DEFAULT_TAB;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <SectionTabBar tabs={TABS} active={tab} />
      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "meetings" && <ConversationsPage />}
        {tab === "memories" && <MemoriesPage />}
        {tab === "rewind" && <AuraPage />}
        {tab === "whispr" && <WhisprPage />}
      </div>
    </div>
  );
}
