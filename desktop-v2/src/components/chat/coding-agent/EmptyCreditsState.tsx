import { Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";

export function EmptyCreditsState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-16 text-center">
      <div className="flex size-14 items-center justify-center rounded-full bg-muted">
        <Wallet className="size-6 text-muted-foreground" />
      </div>
      <div className="space-y-1.5">
        <h3 className="text-base font-semibold text-foreground">
          No coding-agent credits
        </h3>
        <p className="max-w-sm text-sm text-muted-foreground">
          Your coding agent credit balance is empty. Add credits to start
          running agentic coding sessions on your local codebase.
        </p>
      </div>
      {/* onClick intentionally omitted — Stripe integration ships later */}
      <Button variant="outline" disabled>
        Add credits
      </Button>
    </div>
  );
}
