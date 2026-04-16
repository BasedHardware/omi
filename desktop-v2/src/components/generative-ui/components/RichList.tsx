import { ArrowUpRight } from "lucide-react";
import { open as openShell } from "@tauri-apps/plugin-shell";
import { Card, CardContent, CardDescription, CardTitle } from "../../ui/card";
import { ScrollArea, ScrollBar } from "../../ui/scroll-area";
import { cn } from "../../../lib/utils";
import type { RichListItem } from "../types";

export function RichList({ items }: { items: RichListItem[] }) {
  return (
    <div className="not-prose my-3 -mx-1">
      <ScrollArea className="w-full whitespace-nowrap">
        <div className="flex gap-3 px-1 pb-3">
          {items.map((item, i) => (
            <RichListCard key={i} item={item} />
          ))}
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  );
}

function RichListCard({ item }: { item: RichListItem }) {
  const interactive = !!item.url;
  const onClick = () => {
    if (item.url) void openShell(item.url).catch(() => {});
  };

  return (
    <Card
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={interactive ? onClick : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      className={cn(
        "group relative w-[280px] shrink-0 gap-0 overflow-hidden py-0 transition-all",
        interactive &&
          "cursor-pointer hover:border-ring focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] focus-visible:outline-none",
      )}
    >
      {item.thumbnailUrl ? (
        <div className="relative aspect-[16/10] w-full overflow-hidden bg-muted">
          <img
            src={item.thumbnailUrl}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        </div>
      ) : (
        <div className="aspect-[16/10] w-full bg-muted" />
      )}
      <CardContent className="space-y-1 whitespace-normal p-4">
        <CardTitle className="text-sm leading-snug line-clamp-2">
          {item.title}
        </CardTitle>
        {item.description && (
          <CardDescription className="text-xs leading-relaxed line-clamp-3">
            {item.description}
          </CardDescription>
        )}
      </CardContent>
      {interactive && (
        <span className="absolute right-3 top-3 flex size-7 items-center justify-center rounded-full border bg-background/80 text-muted-foreground backdrop-blur-sm transition-colors group-hover:border-ring group-hover:text-foreground">
          <ArrowUpRight className="size-3.5" />
        </span>
      )}
    </Card>
  );
}
