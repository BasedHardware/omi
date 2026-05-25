import envConfig from '@/src/constants/envConfig';
import { Metadata, ResolvingMetadata } from 'next';
import { notFound } from 'next/navigation';
import { ParamsTypes } from '@/src/types/params.types';
import ShareButton from '@/src/components/memories/share-button';

interface DayStats {
  total_conversations: number;
  total_duration_minutes: number;
  action_items_count: number;
}

interface TopicHighlight {
  topic: string;
  emoji: string;
  summary: string;
}

interface ActionItem {
  description: string;
  priority: string;
  completed: boolean;
}

interface DecisionMade {
  decision: string;
}

interface KnowledgeNugget {
  insight: string;
}

interface DailySummary {
  id: string;
  date: string;
  headline: string;
  overview: string;
  day_emoji: string;
  stats: DayStats;
  highlights: TopicHighlight[];
  action_items: ActionItem[];
  decisions_made: DecisionMade[];
  knowledge_nuggets: KnowledgeNugget[];
}

async function getSharedRecap(id: string): Promise<DailySummary | null> {
  try {
    const response = await fetch(`${envConfig.API_URL}/v1/daily-summaries/${id}/shared`, {
      cache: 'no-cache',
    });
    if (!response.ok) return null;
    return (await response.json()) as DailySummary;
  } catch {
    return null;
  }
}

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

export async function generateMetadata(
  { params }: { params: ParamsTypes },
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const prevData = (await parent) as Metadata;
  const recap = await getSharedRecap(params.id);

  const title = recap ? `${recap.day_emoji} ${recap.headline}` : 'Daily Recap';
  const description = recap?.overview ?? 'A daily recap from Omi.';

  return {
    title,
    metadataBase: prevData.metadataBase,
    description,
    robots: { follow: true, index: true },
    openGraph: {
      ...prevData.openGraph,
      title,
      type: 'website',
      url: `${prevData.metadataBase}/recaps/${params.id}`,
      description,
    },
  };
}

export default async function RecapPage({ params }: { params: ParamsTypes }) {
  const recap = await getSharedRecap(params.id);
  if (!recap) notFound();

  const pendingTasks = recap.action_items.filter((i) => !i.completed);

  return (
    <div className="font-system-ui min-h-screen bg-gradient-to-b from-[#1a0a1f] via-[#0a0a2f] to-black">
      <div className="absolute inset-0 bg-[radial-gradient(circle_500px_at_50%_200px,rgba(88,28,135,0.2),transparent)]" />
      <section className="relative mx-auto max-w-screen-md px-6 py-16 md:px-12 md:py-24">
        {/* Header */}
        <div className="mb-10 flex items-start justify-between gap-4">
          <div>
            <p className="mb-2 text-sm text-zinc-500">{formatDate(recap.date)}</p>
            <h1 className="text-2xl font-bold text-white md:text-3xl">
              {recap.day_emoji} {recap.headline}
            </h1>
          </div>
          <ShareButton />
        </div>

        {/* Stats */}
        <div className="mb-8 grid grid-cols-3 gap-3">
          <div className="rounded-2xl bg-zinc-900/70 p-4 text-center ring-1 ring-zinc-800">
            <p className="text-xl font-semibold text-white">
              {recap.stats.total_conversations}
            </p>
            <p className="mt-1 text-xs text-zinc-500">Conversations</p>
          </div>
          <div className="rounded-2xl bg-zinc-900/70 p-4 text-center ring-1 ring-zinc-800">
            <p className="text-xl font-semibold text-white">
              {formatDuration(recap.stats.total_duration_minutes)}
            </p>
            <p className="mt-1 text-xs text-zinc-500">Duration</p>
          </div>
          <div className="rounded-2xl bg-zinc-900/70 p-4 text-center ring-1 ring-zinc-800">
            <p className="text-xl font-semibold text-white">
              {recap.stats.action_items_count}
            </p>
            <p className="mt-1 text-xs text-zinc-500">Tasks</p>
          </div>
        </div>

        {/* Overview */}
        <p className="mb-10 leading-relaxed text-zinc-300">{recap.overview}</p>

        {/* Highlights */}
        {recap.highlights.length > 0 && (
          <section className="mb-8">
            <h2 className="mb-4 text-lg font-semibold text-white">Highlights</h2>
            <div className="space-y-3">
              {recap.highlights.map((h, i) => (
                <div
                  key={i}
                  className="rounded-2xl bg-zinc-900/70 p-4 ring-1 ring-zinc-800"
                >
                  <div className="flex gap-3">
                    <span className="text-xl">{h.emoji}</span>
                    <div>
                      <p className="font-medium text-white">{h.topic}</p>
                      <p className="mt-1 text-sm text-zinc-400">{h.summary}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Tasks */}
        {pendingTasks.length > 0 && (
          <section className="mb-8">
            <h2 className="mb-4 text-lg font-semibold text-white">Tasks</h2>
            <div className="space-y-2">
              {pendingTasks.map((item, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 rounded-2xl bg-zinc-900/70 p-4 ring-1 ring-zinc-800"
                >
                  <div className="mt-0.5 h-4 w-4 shrink-0 rounded-full border border-zinc-600" />
                  <p className="text-sm text-white">{item.description}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Decisions */}
        {recap.decisions_made.length > 0 && (
          <section className="mb-8">
            <h2 className="mb-4 text-lg font-semibold text-white">Decisions</h2>
            <div className="space-y-2">
              {recap.decisions_made.map((d, i) => (
                <div
                  key={i}
                  className="rounded-2xl bg-zinc-900/70 p-4 ring-1 ring-zinc-800"
                >
                  <p className="text-sm text-white">{d.decision}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Learnings */}
        {recap.knowledge_nuggets.length > 0 && (
          <section className="mb-8">
            <h2 className="mb-4 text-lg font-semibold text-white">Learnings</h2>
            <div className="space-y-2">
              {recap.knowledge_nuggets.map((k, i) => (
                <div
                  key={i}
                  className="rounded-2xl bg-zinc-900/70 p-4 ring-1 ring-zinc-800"
                >
                  <p className="text-sm text-white">{k.insight}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Footer */}
        <div className="mt-12 border-t border-zinc-800 pt-8 text-center">
          <p className="text-sm text-zinc-500">
            Generated by{' '}
            <a href="https://omi.me" className="text-purple-400 hover:underline">
              Omi
            </a>{' '}
            — your always-on AI assistant
          </p>
        </div>
      </section>
    </div>
  );
}
