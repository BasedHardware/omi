/**
 * Dashboard — Nooto's home screen.
 *
 * Mirrors the Swift `DashboardPage` but with the upstream v0.11.276 change:
 * the Conversations list was moved to its own sidebar page; the dashboard
 * now has an embedded "Ask Nooto anything" chat input instead.
 *
 * Layout (top → bottom):
 *   1. GreetingHeader   — "Good morning, <name>"
 *   2. AskNootoInput    — compact chat entry, routes to /chat on submit
 *   3. Two-column grid  — Score + Tasks + Goals + Focus (reflows < 960px)
 */

import { GreetingHeader } from "./widgets/GreetingHeader";
import { DailyScoreWidget } from "./widgets/DailyScoreWidget";
import { AskNootoInput } from "./widgets/AskNootoInput";
import { TodaysTasksWidget } from "./widgets/TodaysTasksWidget";
import { ActiveGoalsWidget } from "./widgets/ActiveGoalsWidget";
import { FocusSummaryWidget } from "./widgets/FocusSummaryWidget";

export function DashboardPage() {
  return (
    <div className="dashboard-page">
      <div className="dashboard-scroll">
        <div className="dashboard-content">
          <GreetingHeader />
          <AskNootoInput />

          <div className="dashboard-grid">
            <div className="dashboard-grid-col dashboard-grid-col-primary">
              <TodaysTasksWidget />
              <ActiveGoalsWidget />
            </div>
            <div className="dashboard-grid-col dashboard-grid-col-secondary">
              <DailyScoreWidget />
              <FocusSummaryWidget />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
