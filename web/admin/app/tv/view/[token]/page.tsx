import { resolveActiveTvToken } from "@/lib/tv-links";
import { GrafanaKiosk } from "@/components/dashboard/grafana-kiosk";

export const dynamic = "force-dynamic";

export default async function TvKioskPage(props: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await props.params;
  const link = await resolveActiveTvToken(token);
  if (!link) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-neutral-950 px-6 text-center text-neutral-200">
        <div>
          <h1 className="text-xl font-semibold">Invalid TV link</h1>
          <p className="mt-2 text-sm text-neutral-400">
            This link is missing, expired, or revoked. Ask an admin to generate
            a new one from TV wall links.
          </p>
        </div>
      </main>
    );
  }

  return <GrafanaKiosk />;
}
