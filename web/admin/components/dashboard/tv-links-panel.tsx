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
import { Tv, Copy, Trash2, ArrowLeft, ExternalLink } from "lucide-react";

type TvLinkRow = {
  id: string;
  prefix: string;
  token: string | null;
  path: string | null;
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

function absoluteUrl(path: string | null): string | null {
  if (!path) return null;
  if (typeof window === "undefined") return path;
  return `${window.location.origin}${path}`;
}

async function copyText(text: string) {
  await navigator.clipboard.writeText(text);
}

/** Create / list / revoke secret kiosk URLs. Board is only via those links. */
export function TvLinksPanel() {
  const { fetchWithAuth, token } = useAuthFetch();
  const { loading: authLoading } = useAuthToken();
  const [links, setLinks] = useState<TvLinkRow[]>([]);
  const [label, setLabel] = useState("Office TV");
  const [ttlDays, setTtlDays] = useState("90");
  const [includeRevenue, setIncludeRevenue] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

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

  const markCopied = (id: string) => {
    setCopiedId(id);
    window.setTimeout(() => setCopiedId((cur) => (cur === id ? null : cur)), 1500);
  };

  const onCreate = async () => {
    setBusy(true);
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
      const url = data.url || (data.path ? absoluteUrl(data.path) : null);
      if (url) {
        await copyText(url);
        markCopied(data.link?.id || "new");
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onCopy = async (row: TvLinkRow) => {
    const url = absoluteUrl(row.path);
    if (!url) {
      setError("This legacy link has no stored token — revoke and create a new one.");
      return;
    }
    try {
      await copyText(url);
      markCopied(row.id);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Copy failed");
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
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Tv className="h-7 w-7" />
            TV wall links
          </h2>
          <p className="text-muted-foreground text-sm mt-1 max-w-2xl">
            Secret kiosk URLs for office displays. No Google login on the TV.
            Copy anytime from the list. Revoke to kill a link. This is the only way
            to open the TV board.
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/dashboard">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Dashboard
          </Link>
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Create link</CardTitle>
          <CardDescription>
            Default expiry 90 days. New links are copied to the clipboard automatically
            and stay copyable from the table below.
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Existing links</CardTitle>
          <CardDescription>
            Copy opens the full kiosk URL. Legacy rows created before token storage
            need to be recreated to copy.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th className="py-2 pr-3">Label</th>
                  <th className="py-2 pr-3">URL</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3">Revenue</th>
                  <th className="py-2 pr-3">Created</th>
                  <th className="py-2 pr-3">Expires</th>
                  <th className="py-2 pr-3">Last used</th>
                  <th className="py-2"> </th>
                </tr>
              </thead>
              <tbody>
                {links.map((l) => {
                  const url = absoluteUrl(l.path);
                  return (
                    <tr key={l.id} className="border-b border-border/60">
                      <td className="py-2 pr-3 font-medium">{l.label}</td>
                      <td className="py-2 pr-3 max-w-[18rem]">
                        {url ? (
                          <code className="text-xs break-all">{url}</code>
                        ) : (
                          <span className="text-muted-foreground text-xs">
                            {l.prefix}… (recreate to copy)
                          </span>
                        )}
                      </td>
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
                        <div className="flex items-center gap-1 justify-end">
                          {url && l.status === "active" ? (
                            <>
                              <Button
                                size="sm"
                                variant="ghost"
                                disabled={busy}
                                onClick={() => void onCopy(l)}
                                aria-label={`Copy ${l.label}`}
                                title="Copy URL"
                              >
                                <Copy className="h-4 w-4" />
                                {copiedId === l.id ? (
                                  <span className="ml-1 text-xs">Copied</span>
                                ) : null}
                              </Button>
                              <Button size="sm" variant="ghost" asChild>
                                <a href={url} target="_blank" rel="noreferrer" title="Open">
                                  <ExternalLink className="h-4 w-4" />
                                </a>
                              </Button>
                            </>
                          ) : null}
                          {l.status === "active" && (
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={busy}
                              onClick={() => void onRevoke(l.id)}
                              aria-label={`Revoke ${l.label}`}
                              title="Revoke"
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
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
