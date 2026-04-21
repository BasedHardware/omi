/**
 * AudioSourceSelector — compact dropdown for picking the live audio input.
 *
 * Mirrors the Swift `AudioSourceSelector` so the user can choose between
 * capturing the microphone, the system output, or both. The `audio-capture`
 * plugin defaults to capturing both (`capture_system_audio = true`); until
 * it exposes runtime switching, this component drives UI-only state that
 * we persist to localStorage so the user's preference survives reloads.
 * When the plugin grows runtime control, we'll forward the change through
 * `audioCapture.ts` without changing the component surface.
 */

import { useState } from "react";
import { Headphones, Mic, Volume2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type AudioSource = "microphone" | "system" | "both";

const STORAGE_KEY = "nooto.audio.source";

function readStoredSource(): AudioSource {
  if (typeof window === "undefined") return "both";
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === "microphone" || v === "system" || v === "both") return v;
  } catch {
    // ignore
  }
  return "both";
}

function persist(source: AudioSource): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, source);
  } catch {
    // ignore
  }
}

const SOURCE_META: Record<
  AudioSource,
  {
    label: string;
    short: string;
    description: string;
    Icon: typeof Mic;
  }
> = {
  microphone: {
    label: "Microphone",
    short: "Mic",
    description: "Only your mic — quieter rooms, private notes.",
    Icon: Mic,
  },
  system: {
    label: "System audio",
    short: "System",
    description: "Everything playing on this computer (meetings, calls).",
    Icon: Volume2,
  },
  both: {
    label: "Microphone + System",
    short: "Mic + System",
    description: "You and the room — recommended for calls and meetings.",
    Icon: Headphones,
  },
};

export interface AudioSourceSelectorProps {
  /** Disable the control (e.g. while recording). */
  disabled?: boolean;
  /** Compact button style used inside the Floating Bar. */
  compact?: boolean;
  /** Notified when the user picks a new source. */
  onChange?: (source: AudioSource) => void;
  className?: string;
}

export function AudioSourceSelector({
  disabled = false,
  compact = false,
  onChange,
  className,
}: AudioSourceSelectorProps) {
  const [source, setSource] = useState<AudioSource>(() => readStoredSource());
  const meta = SOURCE_META[source];
  const Icon = meta.Icon;

  const pick = (next: AudioSource) => {
    setSource(next);
    persist(next);
    onChange?.(next);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size={compact ? "xs" : "sm"}
          disabled={disabled}
          className={cn(
            "gap-1.5 text-xs font-normal text-muted-foreground hover:text-foreground",
            className,
          )}
          aria-label="Audio source"
        >
          <Icon className="size-3.5" />
          <span>{compact ? meta.short : meta.label}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="text-xs font-medium">
          Audio source
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {(Object.keys(SOURCE_META) as AudioSource[]).map((key) => {
          const opt = SOURCE_META[key];
          const OptIcon = opt.Icon;
          const selected = key === source;
          return (
            <DropdownMenuItem
              key={key}
              onSelect={() => pick(key)}
              className={cn(
                "flex items-start gap-2",
                selected && "bg-accent/70",
              )}
            >
              <OptIcon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
              <div className="flex min-w-0 flex-col">
                <span className="text-sm font-medium">{opt.label}</span>
                <span className="text-[11px] leading-snug text-muted-foreground">
                  {opt.description}
                </span>
              </div>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
