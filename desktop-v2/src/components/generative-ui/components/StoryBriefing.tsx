import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../ui/card";
import type { StoryBriefingData } from "../types";
import { Timeline } from "./Timeline";
import { QuoteBoard } from "./QuoteBoard";
import { Followups } from "./Followups";

export function StoryBriefing({ data }: { data: StoryBriefingData }) {
  const hasTimeline = !!data.timeline && data.timeline.events.length > 0;
  const hasQuotes = !!data.quoteBoard && data.quoteBoard.quotes.length > 0;
  const hasFollowups = !!data.followups && data.followups.items.length > 0;
  if (!hasTimeline && !hasQuotes && !hasFollowups) return null;

  const sections = [hasTimeline, hasQuotes, hasFollowups].filter(Boolean).length;

  return (
    <Card className="not-prose my-3 gap-0 border-border/60 py-0">
      <CardHeader className="border-b border-border/40 px-5 py-3">
        <CardTitle className="text-sm">Story briefing</CardTitle>
        <CardDescription className="text-xs">
          {sections} {sections === 1 ? "section" : "sections"}
        </CardDescription>
        <CardAction />
      </CardHeader>
      <CardContent className="divide-y divide-border/40 p-0">
        {hasTimeline && (
          <section className="px-5 py-4">
            <h3 className="mb-3 text-sm font-semibold text-foreground">Timeline</h3>
            <Timeline data={data.timeline!} embedded />
          </section>
        )}
        {hasQuotes && (
          <section className="px-5 py-4">
            <h3 className="mb-3 text-sm font-semibold text-foreground">Quotes</h3>
            <QuoteBoard data={data.quoteBoard!} />
          </section>
        )}
        {hasFollowups && (
          <section className="px-5 py-4">
            <h3 className="mb-3 text-sm font-semibold text-foreground">Follow-ups</h3>
            <Followups data={data.followups!} />
          </section>
        )}
      </CardContent>
    </Card>
  );
}
