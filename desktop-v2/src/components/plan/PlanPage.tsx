import { Navigate, useLocation } from "react-router-dom";
import { ListTodo, Target, Lightbulb } from "lucide-react";
import { TasksPage } from "../tasks/TasksPage";
import { GoalsPage } from "../goals/GoalsPage";
import { InsightsPage } from "../insights/InsightsPage";
import {
  SectionTabBar,
  type SectionTabDef,
} from "../library/SectionTabBar";

type PlanTab = "tasks" | "goals" | "insights";

const TABS: SectionTabDef<PlanTab>[] = [
  { id: "tasks", label: "Tasks", icon: ListTodo, path: "/plan/tasks" },
  { id: "goals", label: "Goals", icon: Target, path: "/plan/goals" },
  { id: "insights", label: "Insights", icon: Lightbulb, path: "/plan/insights" },
];

const DEFAULT_TAB: PlanTab = "tasks";

export function PlanPage() {
  const { pathname } = useLocation();

  if (pathname === "/plan" || pathname === "/plan/") {
    return <Navigate to={`/plan/${DEFAULT_TAB}`} replace />;
  }

  const tab = TABS.find((t) => pathname.startsWith(t.path))?.id ?? DEFAULT_TAB;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <SectionTabBar tabs={TABS} active={tab} />
      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "tasks" && <TasksPage />}
        {tab === "goals" && <GoalsPage />}
        {tab === "insights" && <InsightsPage />}
      </div>
    </div>
  );
}
