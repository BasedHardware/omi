import { Card, CardContent, CardFooter } from "../../ui/card";
import { Badge } from "../../ui/badge";
import type { Quote, QuoteBoardData, QuoteRecordStatus } from "../types";

const STATUS_LABEL: Record<QuoteRecordStatus, string> = {
  onTheRecord: "On the record",
  background: "Background",
  offTheRecord: "Off the record",
  unclear: "Unclear",
};

const STATUS_VARIANT: Record<
  QuoteRecordStatus,
  React.ComponentProps<typeof Badge>["variant"]
> = {
  onTheRecord: "default",
  background: "secondary",
  offTheRecord: "destructive",
  unclear: "outline",
};

export function QuoteBoard({ data }: { data: QuoteBoardData }) {
  return (
    <div className="not-prose my-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {data.quotes.map((q, i) => (
        <QuoteCard key={i} quote={q} />
      ))}
    </div>
  );
}

function QuoteCard({ quote }: { quote: Quote }) {
  return (
    <Card className="gap-0 border-border/60 py-0">
      <CardContent className="px-5 pt-5">
        <blockquote className="relative font-serif text-sm italic leading-relaxed text-foreground">
          <span
            aria-hidden
            className="absolute -left-1 -top-2 font-serif text-3xl leading-none text-muted-foreground/40"
          >
            &ldquo;
          </span>
          <span className="relative">{quote.quote}</span>
        </blockquote>
      </CardContent>
      <CardFooter className="flex items-center justify-between border-t border-border/40 px-5 py-3 text-xs">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium text-foreground">
            {quote.speaker}
          </span>
          {quote.time && (
            <span className="font-mono text-muted-foreground tabular-nums">
              · {quote.time}
            </span>
          )}
        </div>
        <Badge variant={STATUS_VARIANT[quote.recordStatus]} className="font-normal">
          {STATUS_LABEL[quote.recordStatus]}
        </Badge>
      </CardFooter>
    </Card>
  );
}
