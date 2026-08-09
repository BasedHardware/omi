"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAuthFetch, useAuthToken } from "@/hooks/useAuthToken";
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
import { Tv, Copy, Trash2, ArrowLeft } from "lucide-react";

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

function parseTtlDays(
  raw: string,
): { ok: true; value: number | null } | { ok: false; error: string } {
  const trimmed = raw.trim();
  if (trimmed === "" || trimmed === "0") return { ok: true, value: null };
  const n = Number(trimmed);
  if (!Number.isFinite(n) || !Number.isInteger(n) || n < 1) {
    return {
      ok: false,
      error: "Expiry must be a positive whole number of days, or empty for never.",
    };
  }
  if (n > 3650) {
    return { ok: false, error: "Expiry cannot exceed 3650 days." };
  }
  return { ok: true, value: n };
}

type Props = {
  /** page = full manage UI; used on /dashboard/tv-links */
  variant?: "page";
};

/** Create / list / revoke secret kiosk URLs. Board is only via those links. */
export function TvLinksPanel({ variant = "page" }: Props) {
  const { fetchWithAuth, token } = useAuthFetch();
  const { loading: authLoading } = useAuthToken();
  const [links, setLinks] = useState<TvLinkRow[]>([]);
  const [label, setLabel] = useState("Office TV");
  const [ttlDays, setTtlDays] = useState("90");
  const [includeRevenue, setIncludeRevenue] = useState(true);
  const [createdUrl, setCreatedUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetchWithAuth("/api/omi/tv-links");
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setLinks([]);
        setError(body.error || `Failed to load TV links (${res.status})`);
        return;
      }
      const data = await res.json();
      setLinks(data.links || []);
      setError(null);
    } catch (e) {
      setLinks([]);
      setError(e instanceof Error ? e.message : "Failed to load TV links");
    }
  }, [fetchWithAuth, token]);

  useEffect(() => {
    if (authLoading) return;
    if (!token) {
      setError("Sign in required to manage TV links");
      return;
    }
    void refresh();
  }, [authLoading, token, refresh]);

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
    <div className="space-y-4">
      {variant === "page" ? (
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-3xl font-bold tracking-tight flex items-center gap-2">
              <Tv className="h-7 w-7" />
              TV wall links
            </h2>
            <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
              Secret kiosk URLs for office displays. No Google login on the TV —
              create a link and open it on the wall. Revoke anytime. Metrics only
              (ARR optional). This is the only way to open the TV board.
            </p>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link href="/dashboard">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Dashboard
            </Link>
          </Button>
        </div>
      ) : null}

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Create link</CardTitle>
          <CardDescription>
            Default expiry 90 days. Full token is shown once — copy it to the TV browser.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="tv-label">Label</Label>
              <Input
                id="tv-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Office TV"
              />
            </div>
            <div className="space-y-2">
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
          <Button onClick={() => void onCreate()} disabled={busy || !token}>
            Generate TV link
          </Button>

          {createdUrl && (
            <div className="rounded-md border bg-muted/40 p-3 space-y-2">
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Existing links</CardTitle>
          <CardDescription>
            Only a short prefix is stored for display. Revoke to kill a leaked URL.
          </CardDescription>
        </CardHeader>
        <CardContent>
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
                {links.length === 0 && !error && (
                  <tr>
                    <td colSpan={8} className="py-6 text-muted-foreground text-center">
                      {authLoading || !token
                        ? "Loading…"
                        : "No TV links yet — generate one to open the wall view"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
