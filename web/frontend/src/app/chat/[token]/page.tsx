import getSharedChat from '@/src/actions/chat/get-shared-chat';
import envConfig from '@/src/constants/envConfig';
import { Metadata, ResolvingMetadata } from 'next';
import { headers } from 'next/headers';
import Image from 'next/image';
import { notFound } from 'next/navigation';

interface ChatParams {
  token: string;
}

interface ChatPageProps {
  params: ChatParams;
}

export async function generateMetadata(
  { params }: { params: ChatParams },
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const prevData = (await parent) as Metadata;
  let data: { sender_name?: string; count?: number } | null = null;

  try {
    const response = await fetch(
      `${envConfig.API_URL}/v2/messages/shared/${params.token}`,
      { next: { revalidate: 60 } },
    );
    if (response.ok) {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        data = await response.json();
      }
    }
  } catch {
    // Silently handle metadata fetch failures.
  }

  const title = !data
    ? 'Shared Chat Not Found'
    : `${data.sender_name} shared a chat with you`;
  const description = !data
    ? 'Open in Omi to view this shared conversation.'
    : `View ${data.count} message${data.count === 1 ? '' : 's'} shared from Omi.`;

  return {
    title,
    metadataBase: prevData.metadataBase,
    description,
    openGraph: {
      ...prevData.openGraph,
      title,
      type: 'website',
      url: new URL(`/chat/${params.token}`, prevData.metadataBase).toString(),
      description,
    },
    other: {
      'apple-itunes-app': 'app-id=6502156163',
      'google-play-app': 'app-id=com.friend.ios',
    },
  };
}

function getPlatformLink(userAgent: string, token: string) {
  const isAndroid = /android/i.test(userAgent);
  const isIOS = /iphone|ipad|ipod/i.test(userAgent);

  return isAndroid
    ? `intent://h.omi.me/chat/${token}#Intent;scheme=https;package=com.friend.ios;S.browser_fallback_url=${encodeURIComponent(
        'https://play.google.com/store/apps/details?id=com.friend.ios',
      )};end`
    : isIOS
      ? `omi://h.omi.me/chat/${token}`
      : 'https://omi.me';
}

function formatTimestamp(timestamp: string | null) {
  if (!timestamp) {
    return null;
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export default async function SharedChatPage({ params }: ChatPageProps) {
  const token = params.token;
  const data = await getSharedChat(token);
  if (!data) {
    notFound();
  }

  const userAgent = headers().get('user-agent') || '';
  const link = getPlatformLink(userAgent, token);

  return (
    <div className="font-system-ui min-h-screen overflow-x-hidden bg-gradient-to-b from-[#1a0a1f] via-[#0a0a2f] to-black">
      <div className="absolute inset-0 bg-[radial-gradient(circle_500px_at_50%_200px,rgba(88,28,135,0.2),transparent)]" />
      <section className="relative mx-auto max-w-screen-md px-6 pb-16 pt-24 md:px-12 md:pb-24 md:pt-32">
        <div className="mb-8 text-center">
          <h1 className="break-words text-2xl font-bold text-white sm:text-3xl md:text-4xl">
            {data.sender_name} shared a chat
          </h1>
          <p className="mt-3 break-words text-lg text-gray-400">
            View the conversation or open it in Omi
          </p>
        </div>

        <div className="mb-10 space-y-4">
          {data.messages.map((message) => {
            const isUser = message.sender === 'human' || message.sender === 'user';
            const timestamp = formatTimestamp(message.created_at);

            return (
              <div
                key={message.id}
                className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-5 py-4 backdrop-blur-sm ${
                    isUser
                      ? 'bg-white/12 border border-white/15 text-white'
                      : 'bg-fuchsia-500/12 border border-fuchsia-500/20 text-white'
                  }`}
                >
                  <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-white/55">
                    {isUser ? data.sender_name : 'omi'}
                  </p>
                  <p className="whitespace-pre-wrap break-words text-base leading-7">
                    {message.text || '(empty message)'}
                  </p>
                  {timestamp && <p className="mt-3 text-xs text-white/45">{timestamp}</p>}
                </div>
              </div>
            );
          })}
        </div>

        <div className="text-center">
          <a
            href={link}
            className="inline-block rounded-2xl bg-white px-10 py-4 text-lg font-semibold text-black transition-all duration-300 hover:translate-y-[-2px] hover:bg-gray-100"
          >
            Open in Omi
          </a>

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
