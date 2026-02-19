import getSharedTasks from '@/src/actions/tasks/get-shared-tasks';
import envConfig from '@/src/constants/envConfig';
import { Metadata, ResolvingMetadata } from 'next';
import { headers } from 'next/headers';
import Image from 'next/image';
import { notFound } from 'next/navigation';

interface TasksParams {
  token: string;
}

interface TasksPageProps {
  params: TasksParams;
}

export async function generateMetadata(
  { params }: { params: TasksParams },
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const prevData = (await parent) as Metadata;
  let data: { sender_name?: string; count?: number } | null = null;

  try {
    const response = await fetch(
      `${envConfig.API_URL}/v1/action-items/shared/${params.token}`,
      { next: { revalidate: 60 } },
    );
    if (response.ok) {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        data = await response.json();
      }
    }
  } catch (error) {
    // Silently handle errors in metadata generation
  }

  const title = !data
    ? 'Shared Tasks Not Found'
    : `${data.sender_name} shared ${data.count} task${
        data.count === 1 ? '' : 's'
      } with you`;

  return {
    title: title,
    metadataBase: prevData.metadataBase,
    description: 'Open in Omi to add these tasks to your list.',
    openGraph: {
      ...prevData.openGraph,
      title: title,
      type: 'website',
      url: new URL(`/tasks/${params.token}`, prevData.metadataBase).toString(),
      description: 'Open in Omi to add these tasks to your list.',
    },
    other: {
      'apple-itunes-app': `app-id=6502156163`,
      'google-play-app': `app-id=com.friend.ios`,
    },
  };
}

function getPlatformLink(userAgent: string, token: string) {
  const isAndroid = /android/i.test(userAgent);
  const isIOS = /iphone|ipad|ipod/i.test(userAgent);

  // iOS: Use custom URL scheme because Universal Links don't trigger for same-domain navigation
  // (user is already on h.omi.me, so tapping https://h.omi.me/... just reloads the page)
  // Android: Use intent:// with fallback to Google Play if app not installed
  return isAndroid
    ? `intent://h.omi.me/tasks/${token}#Intent;scheme=https;package=com.friend.ios;S.browser_fallback_url=${encodeURIComponent(
        'https://play.google.com/store/apps/details?id=com.friend.ios',
      )};end`
    : isIOS
    ? `omi://h.omi.me/tasks/${token}`
    : 'https://omi.me';
}

function formatDueDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default async function SharedTasksPage({ params }: TasksPageProps) {
  const token = params.token;
  const data = await getSharedTasks(token);
  if (!data) {
    notFound();
  }

  const userAgent = headers().get('user-agent') || '';
  const link = getPlatformLink(userAgent, token);

  return (
    <div className="font-system-ui min-h-screen overflow-x-hidden bg-gradient-to-b from-[#1a0a1f] via-[#0a0a2f] to-black">
      <div className="absolute inset-0 bg-[radial-gradient(circle_500px_at_50%_200px,rgba(88,28,135,0.2),transparent)]" />
      <section className="relative mx-auto max-w-screen-md px-6 pb-16 pt-24 md:px-12 md:pb-24 md:pt-32">
        {/* Sender info */}
        <div className="mb-8 text-center">
          <h1 className="break-words text-2xl font-bold text-white sm:text-3xl md:text-4xl">
            {data.sender_name} shared {data.count} task{data.count === 1 ? '' : 's'}
          </h1>
          <p className="mt-3 break-words text-lg text-gray-400">
            Open in Omi to add {data.count === 1 ? 'it' : 'them'} to your list
          </p>
        </div>

        {/* Task list */}
        <div className="mb-10 space-y-3">
          {data.tasks.map((task, index) => (
            <div
              key={index}
              className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/5 px-5 py-4 backdrop-blur-sm"
            >
              <div className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded border border-white/20">
                {/* Empty checkbox */}
              </div>
              <div className="min-w-0 flex-1">
                <p className="break-words text-base text-white">{task.description}</p>
                {task.due_at && (
                  <p className="mt-1 text-sm text-gray-400">
                    Due {formatDueDate(task.due_at)}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* CTA button */}
        <div className="text-center">
          <a
            href={link}
            className="inline-block rounded-2xl bg-white px-10 py-4 text-lg font-semibold text-black transition-all duration-300 hover:translate-y-[-2px] hover:bg-gray-100"
          >
            Open in Omi
          </a>

          {/* Store badges */}
          <div className="mt-6 flex items-center justify-center gap-4">
            <a
              href="https://apps.apple.com/us/app/friend-ai-wearable/id6502156163"
              target="_blank"
              rel="noopener noreferrer"
              className="transition-transform duration-300 hover:scale-105"
            >
              <Image
                src="/app-store-badge.svg"
                alt="Download on the App Store"
                className="h-[40px]"
                width={120}
                height={40}
              />
            </a>
            <a
              href="https://play.google.com/store/apps/details?id=com.friend.ios"
              target="_blank"
              rel="noopener noreferrer"
              className="transition-transform duration-300 hover:scale-105"
            >
              <Image
                src="/google-play-badge.png"
                alt="Get it on Google Play"
                className="h-[40px]"
                width={135}
                height={40}
              />
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
