"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuthFetch } from "@/hooks/useAuthToken";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tv, Copy, Trash2 } from "lucide-react";

type TvLinkRow = {
  id: string;
  prefix: string;
  label: string;
  createdBy: string;
  createdAt: number;
  expiresAt: number | null;
  revokedAt: number | null;
  lastUsedAt: number | null;
  includeRevenue: boolean;
  status: "active" | "expired" | "revoked";
};

function parseTtlDays(raw: string): { ok: true; value: number | null } | { ok: false; error: string } {
  const trimmed = raw.trim();
  if (trimmed === "" || trimmed === "0") return { ok: true, value: null };
  const n = Number(trimmed);
  if (!Number.isFinite(n) || !Number.isInteger(n) || n < 1) {
    return { ok: false, error: "Expiry must be a positive whole number of days, or empty for never." };
  }
  if (n > 3650) {
    return { ok: false, error: "Expiry cannot exceed 3650 days." };
  }
  return { ok: true, value: n };
}

/** Create / list / revoke secret kiosk URLs. Board is only available via those links. */
export function TvLinksPanel() {
  const { fetchWithAuth } = useAuthFetch();
  const [links, setLinks] = useState<TvLinkRow[]>([]);
  const [label, setLabel] = useState("Office TV");
  const [ttlDays, setTtlDays] = useState("90");
  const [includeRevenue, setIncludeRevenue] = useState(true);
  const [createdUrl, setCreatedUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetchWithAuth("/api/omi/tv-links");
      if (!res.ok) {
        setLinks([]);
        setError("Failed to load TV links");
        return;
      }
      const data = await res.json();
      setLinks(data.links || []);
      setError(null);
    } catch (e) {
      setLinks([]);
      setError(e instanceof Error ? e.message : "Failed to load TV links");
    }
  }, [fetchWithAuth]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onCreate = async () => {
    setBusy(true);
    setCreatedUrl(null);
    try {
      const parsed = parseTtlDays(ttlDays);
      if (!parsed.ok) {
        setError(parsed.error);
        return;
      }
      const res = await fetchWithAuth("/api/omi/tv-links", {
        method: "POST",
        body: JSON.stringify({
          label,
          ttlDays: parsed.value,
          includeRevenue,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Create failed");
      setCreatedUrl(data.url || data.path);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onRevoke = async (id: string) => {
    if (!confirm("Revoke this TV link? The wall URL will stop working immediately.")) {
      return;
    }
    setBusy(true);
    try {
      const res = await fetchWithAuth(`/api/omi/tv-links/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Revoke failed");
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card id="tv-links">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-xl">
          <Tv className="h-5 w-5" />
          TV wall links
        </CardTitle>
        <CardDescription>
          Secret kiosk URLs for office displays. No Google login on the TV — create a
          link and open it on the wall. Revoke anytime. Metrics only (ARR optional).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
          <div className="text-sm font-medium">Create link</div>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="tv-label">Label</Label>
              <Input
                id="tv-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Office TV"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tv-ttl">Expiry (days, empty = never)</Label>
              <Input
                id="tv-ttl"
                value={ttlDays}
                onChange={(e) => setTtlDays(e.target.value)}
                placeholder="90"
                inputMode="numeric"
              />
            </div>
            <div className="flex items-end gap-2 pb-2">
              <Switch
                id="tv-rev"
                checked={includeRevenue}
                onCheckedChange={setIncludeRevenue}
              />
              <Label htmlFor="tv-rev">Include ARR / MRR</Label>
            </div>
          </div>
          <Button onClick={() => void onCreate()} disabled={busy} size="sm">
            Generate TV link
          </Button>

          {createdUrl && (
            <div className="rounded-md border bg-background p-3 space-y-2">
              <div className="text-sm font-medium">Copy now — not shown again</div>
              <div className="flex gap-2 items-center">
                <code className="text-xs break-all flex-1">{createdUrl}</code>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => void navigator.clipboard.writeText(createdUrl)}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b">
                <th className="py-2 pr-3">Label</th>
                <th className="py-2 pr-3">Prefix</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Revenue</th>
                <th className="py-2 pr-3">Created</th>
                <th className="py-2 pr-3">Expires</th>
                <th className="py-2 pr-3">Last used</th>
                <th className="py-2"> </th>
              </tr>
            </thead>
            <tbody>
              {links.map((l) => (
                <tr key={l.id} className="border-b border-border/60">
                  <td className="py-2 pr-3 font-medium">{l.label}</td>
                  <td className="py-2 pr-3 font-mono text-xs">{l.prefix}…</td>
                  <td className="py-2 pr-3">{l.status}</td>
                  <td className="py-2 pr-3">{l.includeRevenue ? "yes" : "no"}</td>
                  <td className="py-2 pr-3 whitespace-nowrap">
                    {new Date(l.createdAt).toLocaleString()}
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap">
                    {l.expiresAt ? new Date(l.expiresAt).toLocaleDateString() : "never"}
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap">
                    {l.lastUsedAt ? new Date(l.lastUsedAt).toLocaleString() : "—"}
                  </td>
                  <td className="py-2">
                    {l.status === "active" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => void onRevoke(l.id)}
                        aria-label={`Revoke ${l.label}`}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
              {links.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-6 text-muted-foreground text-center">
                    No TV links yet — generate one to open the wall view
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
