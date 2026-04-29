/**
 * Inline command palette that pops above the prompt textarea when the user
 * types `/`. Filters as they type after the slash, supports arrow-key nav +
 * Enter to insert.
 *
 * Designed to be used from CodingAgentSession — the parent owns the open
 * state (driven by `parseSlashQuery(inputText)`) and intercepts arrow / Enter
 * keys on the textarea, forwarding them via the imperative ref.
 */

import { forwardRef, useImperativeHandle, useMemo, useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { filterCommands, type SlashCommand } from "./slashCommands";

export interface SlashCommandMenuHandle {
  /** Move highlight up/down and return whether the event was consumed. */
  move: (delta: 1 | -1) => boolean;
  /** Select the highlighted command and return it (or null if menu empty). */
  selectActive: () => SlashCommand | null;
}

interface Props {
  query: string;
  onSelect: (cmd: SlashCommand) => void;
}

export const SlashCommandMenu = forwardRef<SlashCommandMenuHandle, Props>(
  function SlashCommandMenu({ query, onSelect }, ref) {
    const items = useMemo(() => filterCommands(query), [query]);
    const [active, setActive] = useState(0);

    // Reset highlight when the filter changes so the first item is always lit.
    useEffect(() => {
      setActive(0);
    }, [query]);

    useImperativeHandle(
      ref,
      () => ({
        move: (delta) => {
          if (items.length === 0) return false;
          setActive((i) => (i + delta + items.length) % items.length);
          return true;
        },
        selectActive: () => items[active] ?? null,
      }),
      [items, active],
    );

    if (items.length === 0) {
      return (
        <div className="mb-2 rounded-lg border border-border bg-popover px-3 py-2 text-xs text-muted-foreground shadow-sm">
          No commands match <span className="font-mono">/{query}</span>
        </div>
      );
    }

    // Group items by their declared group while preserving the filter order.
    const grouped: Record<string, SlashCommand[]> = {};
    for (const cmd of items) {
      (grouped[cmd.group] ??= []).push(cmd);
    }

    let runningIndex = 0;
    return (
      <div className="mb-2 max-h-64 overflow-y-auto rounded-lg border border-border bg-popover shadow-sm">
        {Object.entries(grouped).map(([group, cmds], gi) => (
          <div key={group} className={cn(gi > 0 && "border-t border-border")}>
            <div className="px-3 pt-2 pb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {group}
            </div>
            {cmds.map((cmd) => {
              const idx = runningIndex++;
              const isActive = idx === active;
              return (
                <button
                  key={cmd.name}
                  type="button"
                  onMouseEnter={() => setActive(idx)}
                  onClick={() => onSelect(cmd)}
                  className={cn(
                    "flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left transition-colors",
                    isActive ? "bg-accent text-accent-foreground" : "hover:bg-accent/50",
                  )}
                >
                  <span className="font-mono text-xs text-foreground">/{cmd.name}</span>
                  <span className="text-xs text-muted-foreground">{cmd.description}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    );
  },
);
