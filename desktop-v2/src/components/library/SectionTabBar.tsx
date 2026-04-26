import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

export type SectionTabDef<TId extends string> = {
  id: TId;
  label: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
};

export function SectionTabBar<TId extends string>({
  tabs,
  active,
}: {
  tabs: SectionTabDef<TId>[];
  active: TId;
}) {
  return (
    <div className="flex shrink-0 items-center gap-1 border-b border-border/40 bg-secondary/30 px-4 py-1.5">
      {tabs.map((t) => {
        const Icon = t.icon;
        const isActive = t.id === active;
        return (
          <NavLink
            key={t.id}
            to={t.path}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors",
              isActive
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:bg-accent/40 hover:text-foreground",
            )}
          >
            <Icon className="size-3.5" />
            <span>{t.label}</span>
          </NavLink>
        );
      })}
    </div>
  );
}
