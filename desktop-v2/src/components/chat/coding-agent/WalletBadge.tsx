import { useEffect, useState } from "react";
import { Wallet } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { api, ApiError } from "@/services/api";

interface WalletData {
  balance_cents: number;
}

interface Props {
  /** Incrementing this triggers a refetch — bump after each agent turn ends. */
  refetchKey?: number;
  onOutOfCredits?: () => void;
}

export function WalletBadge({ refetchKey = 0, onOutOfCredits }: Props) {
  const [balanceCents, setBalanceCents] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    api
      .get<WalletData>("/v1/agent/code/wallet")
      .then((data) => {
        if (cancelled) return;
        setBalanceCents(data.balance_cents);
        if (data.balance_cents === 0) onOutOfCredits?.();
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 402) {
          setBalanceCents(0);
          onOutOfCredits?.();
        }
        // Silently ignore other errors — badge simply stays hidden.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [refetchKey, onOutOfCredits]);

  if (loading || balanceCents === null) return null;

  const dollars = balanceCents / 100;
  const formatted = dollars.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  // Color: muted when > $1, destructive when < $0.50
  const variant =
    balanceCents < 50 ? "destructive" : balanceCents === 0 ? "destructive" : "secondary";

  return (
    <Badge variant={variant} className="gap-1 text-xs tabular-nums">
      <Wallet className="size-3" />
      {formatted}
    </Badge>
  );
}
