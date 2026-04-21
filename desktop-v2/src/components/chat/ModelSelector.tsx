/**
 * Model picker for the chat input bar. Lets the user choose between Claude
 * (with tools), Gemini (no tools), or Auto (Claude when connected, else
 * Gemini). Selecting Claude when no token is present kicks off the OAuth
 * sign-in flow.
 */

import { useMemo } from "react";
import { Check, Sparkles, Wrench, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/stores/chatStore";
import type { ChatModelPreference } from "@/stores/chatStore";
import { useClaudeStore } from "@/stores/claudeStore";

interface ModelMeta {
  id: ChatModelPreference;
  label: string;
  short: string;
  description: string;
  Icon: typeof Sparkles;
}

const MODELS: ModelMeta[] = [
  {
    id: "auto",
    label: "Auto",
    short: "Auto",
    description: "Claude when connected, otherwise Gemini.",
    Icon: Sparkles,
  },
  {
    id: "claude",
    label: "Claude (with tools)",
    short: "Claude",
    description: "Sonnet 4 with task, memory, goal, and screen-history tools.",
    Icon: Wrench,
  },
  {
    id: "gemini",
    label: "Gemini",
    short: "Gemini",
    description: "Gemini 2.5 Flash. Fast, no tool calling.",
    Icon: Zap,
  },
];

export function ModelSelector({ className }: { className?: string }) {
  const model = useChatStore((s) => s.model);
  const setModel = useChatStore((s) => s.setModel);
  const claudeToken = useClaudeStore((s) => s.accessToken);
  const isSigningIn = useClaudeStore((s) => s.isSigningIn);
  const signIn = useClaudeStore((s) => s.signIn);

  const current = useMemo(
    () => MODELS.find((m) => m.id === model) ?? MODELS[0],
    [model],
  );

  // What the chat will *actually* use right now, given the preference + token.
  const effective: ChatModelPreference =
    model === "claude"
      ? claudeToken
        ? "claude"
        : "claude" // selected but unauthed — store will surface the error
      : model === "gemini"
        ? "gemini"
        : claudeToken
          ? "claude"
          : "gemini";

  const handlePick = async (next: ChatModelPreference) => {
    setModel(next);
    if (next === "claude" && !claudeToken && !isSigningIn) {
      try {
        await signIn();
      } catch {
        // signIn already records error in claudeStore
      }
    }
  };

  const Icon = current.Icon;
  const showAutoSuffix = model === "auto";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn(
            "h-7 gap-1.5 px-2 text-xs font-normal text-muted-foreground hover:text-foreground",
            className,
          )}
          aria-label="Model"
        >
          <Icon className="size-3.5" />
          <span>
            {current.short}
            {showAutoSuffix && (
              <span className="text-muted-foreground/60">
                {" "}
                · {effective === "claude" ? "Claude" : "Gemini"}
              </span>
            )}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        <DropdownMenuLabel className="text-xs font-medium">Model</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {MODELS.map((opt) => {
          const OptIcon = opt.Icon;
          const selected = opt.id === model;
          const isClaudeUnconnected = opt.id === "claude" && !claudeToken;
          return (
            <DropdownMenuItem
              key={opt.id}
              onSelect={() => void handlePick(opt.id)}
              className={cn("flex items-start gap-2", selected && "bg-accent/70")}
            >
              <OptIcon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{opt.label}</span>
                  {selected && <Check className="size-3.5 text-foreground" />}
                </div>
                <span className="text-[11px] leading-snug text-muted-foreground">
                  {opt.description}
                  {isClaudeUnconnected && (
                    <span className="text-amber-500">
                      {" "}
                      — selecting will prompt sign-in.
                    </span>
                  )}
                </span>
              </div>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
