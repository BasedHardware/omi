import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useGoalStore } from "@/stores/goalStore";
import type { Goal } from "@/stores/goalStore";
import { PRESET_EMOJI, getEmojiForTitle } from "./emoji";

interface Props {
  open: boolean;
  goal: Goal | null;
  onOpenChange: (open: boolean) => void;
}

export function GoalEditModal({ open, goal, onOpenChange }: Props) {
  const { createGoal, updateGoal, deleteGoal } = useGoalStore();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [currentValue, setCurrentValue] = useState("0");
  const [targetValue, setTargetValue] = useState("10");
  const [selectedEmoji, setSelectedEmoji] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (goal) {
      setTitle(goal.title);
      setDescription(goal.description ?? "");
      setCurrentValue(String(goal.current_value));
      setTargetValue(String(goal.target_value));
      setSelectedEmoji(null);
    } else {
      setTitle("");
      setDescription("");
      setCurrentValue("0");
      setTargetValue("10");
      setSelectedEmoji(null);
    }
  }, [open, goal]);

  const autoEmoji = getEmojiForTitle(title);
  const effectiveEmoji = selectedEmoji ?? autoEmoji;

  const handleSave = async () => {
    const t = title.trim();
    if (!t) return;

    const target = Number.parseFloat(targetValue);
    const current = Number.parseFloat(currentValue);
    if (!Number.isFinite(target) || target <= 0) return;

    setSaving(true);
    try {
      if (goal) {
        await updateGoal(goal.id, {
          title: t,
          description: description.trim() || null,
          target_value: target,
          current_value: Number.isFinite(current) ? current : 0,
          min_value: 0,
          max_value: target,
        });
      } else {
        await createGoal({
          title: t,
          description: description.trim() || null,
          goal_type: "numeric",
          target_value: target,
          current_value: Number.isFinite(current) ? current : 0,
          min_value: 0,
          max_value: target,
          source: "user",
        });
      }
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!goal) return;
    await deleteGoal(goal.id);
    onOpenChange(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void handleSave();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" onKeyDown={handleKeyDown}>
        <DialogHeader>
          <DialogTitle>{goal ? "Edit goal" : "New goal"}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-foreground/5 text-2xl">
              {effectiveEmoji}
            </div>
            <div className="grid grid-cols-10 gap-1">
              {PRESET_EMOJI.map((emo) => (
                <button
                  key={emo}
                  type="button"
                  onClick={() => setSelectedEmoji(emo)}
                  className={`flex h-7 w-7 items-center justify-center rounded text-sm hover:bg-foreground/10 ${
                    selectedEmoji === emo ? "bg-foreground/10" : ""
                  }`}
                  aria-label={`Pick ${emo}`}
                >
                  {emo}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Title</label>
            <Input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Read 12 books this year"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-muted-foreground">
              Description <span className="text-muted-foreground/70">(optional)</span>
            </label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Why this matters"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Current</label>
              <Input
                type="number"
                value={currentValue}
                onChange={(e) => setCurrentValue(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Target</label>
              <Input
                type="number"
                value={targetValue}
                onChange={(e) => setTargetValue(e.target.value)}
              />
            </div>
          </div>
        </div>

        <DialogFooter className="flex flex-row items-center justify-between">
          <div>
            {goal && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleDelete}
                className="text-destructive hover:text-destructive"
              >
                <Trash2 size={14} className="mr-1" /> Delete
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="button" onClick={handleSave} disabled={saving || !title.trim()}>
              {goal ? "Save" : "Create"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
