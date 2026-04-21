/**
 * LiveNameSpeakerSheet — modal for naming a speaker during live recording.
 *
 * Mirrors the Swift `LiveNameSpeakerSheet`: presents the speaker ID, a short
 * preview of their last utterance, any previously used names (chips), and an
 * inline "Add person" input. Saving writes the mapping to
 * `useSpeakerStore`, which reapplies the name across `<SpeakerBubbles>` and
 * the Floating Bar.
 *
 * This sheet is intentionally decoupled from the backend `Person` API — for
 * desktop-v2 we persist locally and let the authoritative person identity
 * be resolved on the server when the meeting is saved.
 */

import { useEffect, useMemo, useState } from "react";
import { Pencil, Plus, User } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useSpeakerStore } from "@/stores/speakerStore";
import { cn } from "@/lib/utils";

export interface LiveNameSpeakerSheetProps {
  /** Controls visibility. When null the sheet is closed. */
  speaker: {
    speaker: string;
    speakerId: number;
    sampleText: string;
  } | null;
  onClose: () => void;
}

/** Truncate a preview utterance for the header card. */
function truncate(text: string, max = 140): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max).trimEnd()}…`;
}

export function LiveNameSpeakerSheet({ speaker, onClose }: LiveNameSpeakerSheetProps) {
  const names = useSpeakerStore((s) => s.names);
  const setName = useSpeakerStore((s) => s.setName);
  const clearName = useSpeakerStore((s) => s.clearName);

  const currentName = speaker ? names[speaker.speaker] ?? "" : "";
  const [selected, setSelected] = useState<string>("");
  const [draftName, setDraftName] = useState<string>("");
  const [warning, setWarning] = useState<string | null>(null);

  // Reset local state whenever we open for a different speaker.
  useEffect(() => {
    if (!speaker) return;
    setSelected(currentName);
    setDraftName("");
    setWarning(null);
  }, [speaker, currentName]);

  // Known-name chips (everyone who's already been named).
  const knownNames = useMemo(() => {
    const set = new Set<string>();
    for (const v of Object.values(names)) {
      if (v && v.trim()) set.add(v.trim());
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [names]);

  if (!speaker) {
    return (
      <Dialog open={false} onOpenChange={(open) => !open && onClose()}>
        <DialogContent />
      </Dialog>
    );
  }

  const validateNewName = (name: string): string | null => {
    const trimmed = name.trim();
    if (!trimmed) return null;
    // Duplicate check is a soft warning — the user can still pick an
    // existing chip if that's what they meant.
    if (knownNames.some((n) => n.toLowerCase() === trimmed.toLowerCase())) {
      return "Someone already uses that name. Pick the chip above instead.";
    }
    return null;
  };

  const handleDraftChange = (value: string) => {
    setDraftName(value);
    setWarning(validateNewName(value));
  };

  const pickChip = (name: string) => {
    setSelected(name);
    setDraftName("");
    setWarning(null);
  };

  const addCustom = () => {
    const trimmed = draftName.trim();
    if (!trimmed) return;
    const warn = validateNewName(trimmed);
    if (warn) return;
    setSelected(trimmed);
    setDraftName("");
    setWarning(null);
  };

  const canSave = selected.trim().length > 0;

  const handleSave = () => {
    if (!canSave) return;
    setName(speaker.speaker, selected.trim());
    onClose();
  };

  const handleClear = () => {
    clearName(speaker.speaker);
    onClose();
  };

  return (
    <Dialog open={true} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>Name this speaker</DialogTitle>
          <DialogDescription>
            Give this voice a name so you can tell people apart in the live
            transcript. The name stays with this device.
          </DialogDescription>
        </DialogHeader>

        {/* Speaker preview card */}
        <div className="flex items-start gap-3 rounded-lg border border-border/60 bg-secondary/40 p-3">
          <div
            className="flex size-9 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold text-foreground"
            aria-hidden="true"
          >
            {speaker.speakerId}
          </div>
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <User className="size-3" />
              Speaker {speaker.speakerId}
            </div>
            {speaker.sampleText ? (
              <p className="line-clamp-3 text-sm italic text-foreground/85">
                "{truncate(speaker.sampleText)}"
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                No sample yet — they haven't spoken a full sentence.
              </p>
            )}
          </div>
        </div>

        {/* Known chips */}
        {knownNames.length > 0 && (
          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              Who is this?
            </span>
            <div className="flex flex-wrap gap-1.5">
              {knownNames.map((name) => {
                const active = selected.trim().toLowerCase() === name.toLowerCase();
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={() => pickChip(name)}
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs transition-colors",
                      active
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-secondary/60 text-foreground hover:bg-secondary",
                    )}
                  >
                    {name}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* New name inline input */}
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium text-muted-foreground">
            Or add a new person
          </span>
          <div className="flex items-center gap-2">
            <Input
              value={draftName}
              onChange={(e) => handleDraftChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addCustom();
                }
              }}
              placeholder="e.g. Alex"
              aria-label="New speaker name"
              className="h-9"
            />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={addCustom}
              disabled={!draftName.trim() || warning !== null}
              className="gap-1.5"
            >
              <Plus className="size-3.5" />
              Add
            </Button>
          </div>
          {warning && (
            <span className="text-[11px] text-destructive">{warning}</span>
          )}
        </div>

        {selected && (
          <div className="flex items-center gap-2 rounded-md border border-primary/40 bg-primary/10 px-3 py-2 text-sm text-foreground">
            <Pencil className="size-3.5 text-primary" />
            <span>
              Save as <span className="font-semibold">{selected}</span>
            </span>
          </div>
        )}

        <DialogFooter className="gap-2 sm:justify-between">
          <div>
            {currentName && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-destructive"
                onClick={handleClear}
              >
                Remove name
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleSave}
              disabled={!canSave}
            >
              Save
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
