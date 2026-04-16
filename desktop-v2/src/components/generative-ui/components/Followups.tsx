import { CheckCircle2, HelpCircle, ShieldCheck, Sparkles } from "lucide-react";
import { Card, CardContent } from "../../ui/card";
import { Badge } from "../../ui/badge";
import type { FollowupType, FollowupsData } from "../types";

const TYPE_LABEL: Record<FollowupType, string> = {
  factCheck: "Fact-check",
  verification: "Verification",
  question: "Question",
  other: "To-do",
};

const TYPE_ICON: Record<FollowupType, typeof CheckCircle2> = {
  factCheck: CheckCircle2,
  verification: ShieldCheck,
  question: HelpCircle,
  other: Sparkles,
};

const TYPE_VARIANT: Record<
  FollowupType,
  React.ComponentProps<typeof Badge>["variant"]
> = {
  factCheck: "default",
  verification: "secondary",
  question: "outline",
  other: "outline",
};

export function Followups({ data }: { data: FollowupsData }) {
  return (
    <ul className="not-prose my-3 space-y-2">
      {data.items.map((item, i) => {
        const Icon = TYPE_ICON[item.type];
        return (
          <li key={i}>
            <Card className="gap-0 border-border/60 py-0">
              <CardContent className="flex items-start gap-3 p-4">
                <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1 space-y-1">
                  <Badge
                    variant={TYPE_VARIANT[item.type]}
                    className="font-normal"
                  >
                    {TYPE_LABEL[item.type]}
                  </Badge>
                  <p className="text-sm leading-relaxed text-foreground">
                    {item.content}
                  </p>
                </div>
              </CardContent>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
