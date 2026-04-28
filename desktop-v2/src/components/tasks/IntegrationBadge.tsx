import { ExternalLink, Layers, Triangle } from "lucide-react";
import type { Task, TaskSource } from "../../stores/taskStore";

const SOURCE_ICON: Record<string, typeof ExternalLink> = {
  jira: Layers,
  linear: Triangle,
};

const SOURCE_LABEL: Record<string, string> = {
  jira: "Jira",
  linear: "Linear",
};

function labelFor(source: TaskSource | undefined, fallback: string | undefined): string {
  if (!source || source === "native") return fallback ?? "App";
  return SOURCE_LABEL[source] ?? fallback ?? source;
}

export function IntegrationBadge({ task }: { task: Task }) {
  if (!task.source || task.source === "native") return null;
  const Icon = SOURCE_ICON[task.source] ?? ExternalLink;
  const label = labelFor(task.source, task.source_app_name);
  // External_id (e.g. WPNG-123) is the most useful glanceable token; fall back
  // to plain source label when a plugin doesn't expose a ticket key.
  const id = task.external_id;
  return (
    <span className="task-chip task-chip-integration" title={`${label}${id ? ` · ${id}` : ""}`}>
      <Icon size={11} />
      <span>{id ?? label}</span>
    </span>
  );
}
