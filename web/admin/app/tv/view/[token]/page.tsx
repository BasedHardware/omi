import { resolveActiveTvToken } from "@/lib/tv-links";
import { buildTvSnapshot, type TvSnapshot } from "@/lib/tv-snapshot";
import { TvBoard } from "@/components/dashboard/tv-board";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

type PageProps = {
  params: Promise<{ token: string }>;
};

/**
 * Public kiosk TV surface. Auth is the path token (capability URL).
 * Snapshot is loaded on the server for first paint; client polls afterward.
 */
export default async function PublicTvViewPage({ params }: PageProps) {
  const { token: raw } = await params;
  const token = typeof raw === "string" ? decodeURIComponent(raw) : "";

  if (!token || token.length < 16) {
    return (
      <div className="min-h-screen grid place-items-center bg-slate-950 text-slate-200">
        Missing TV token
      </div>
    );
  }

  const link = await resolveActiveTvToken(token);
  if (!link) {
    return (
      <div className="min-h-screen grid place-items-center bg-slate-950 text-slate-200 p-6 text-center">
        <div>
          <div className="text-lg font-medium">Invalid or revoked TV link</div>
          <div className="text-sm text-slate-400 mt-2">
            Generate a new link from Admin → TV wall links.
          </div>
        </div>
      </div>
    );
  }

  let initialSnap: TvSnapshot | null = null;
  let initialError: string | null = null;
  try {
    initialSnap = await buildTvSnapshot({ includeRevenue: link.includeRevenue });
  } catch (e) {
    initialError = e instanceof Error ? e.message : String(e);
  }

  return (
    <TvBoard
      token={token}
      kioskLabel={link.label || "Shared link"}
      initialSnap={initialSnap}
      initialError={initialError}
    />
  );
}
