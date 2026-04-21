import { GreetingHeader } from "./widgets/GreetingHeader";
import { DailyScoreWidget } from "./widgets/DailyScoreWidget";
import { AskNootoInput } from "./widgets/AskNootoInput";
import { TodaysTasksWidget } from "./widgets/TodaysTasksWidget";
import { ActiveGoalsWidget } from "./widgets/ActiveGoalsWidget";
import { FocusSummaryWidget } from "./widgets/FocusSummaryWidget";

/**
 * Home screen — bento-style dashboard.
 *
 * Layout:
 *   Row 1: greeting (full width)
 *   Row 2: Ask Nooto (full width, hero composer)
 *   Row 3: Score / Focus / (balance via Goals compact) — 12-col grid
 *          - tasks: 7 cols (primary list)
 *          - goals: 5 cols (compact progress)
 *          On md-: stacks single column
 */
export function DashboardPage() {
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 pb-12 pt-8 md:px-8 md:pt-10">
          <GreetingHeader />
          <AskNootoInput />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-12">
            <div className="md:col-span-4 min-h-0">
              <DailyScoreWidget />
            </div>
            <div className="md:col-span-8 min-h-0">
              <FocusSummaryWidget />
            </div>
            <div className="md:col-span-7 min-h-0">
              <TodaysTasksWidget />
            </div>
            <div className="md:col-span-5 min-h-0">
              <ActiveGoalsWidget />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
