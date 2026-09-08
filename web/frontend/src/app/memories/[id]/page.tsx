import getSharedMemory from '@/src/actions/memories/get-shared-memory';
import Memory from '@/src/components/memories/memory';
import MemoryHeader from '@/src/components/memories/memory-header';
import SharedConversationInstallCta, {
  getConversationSharePlatformLink,
} from '@/src/components/memories/shared-conversation-install-cta';
import envConfig from '@/src/constants/envConfig';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import { markdownToPlainText } from '@/src/lib/markdown-to-plain-text.mjs';
import { ParamsTypes, SearchParamsTypes } from '@/src/types/params.types';
import { Metadata, ResolvingMetadata } from 'next';
import { headers } from 'next/headers';
import { notFound } from 'next/navigation';

interface MemoryPageProps {
  params: Promise<ParamsTypes>;
  searchParams: Promise<SearchParamsTypes>;
}

export async function generateMetadata(
  props: { params: Promise<ParamsTypes> },
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const params = await props.params;
  const prevData = (await parent) as Metadata;
  let memory: { structured?: { title?: string; overview?: string } } | null = null;

  try {
    const response = await fetch(
      `${envConfig.API_URL}/v1/conversations/${params.id}/shared`,
      {
        next: {
          revalidate: 60,
        },
      },
    );

    if (response.ok) {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        memory = await response.json();
      }
    }
  } catch {
    // Silently handle errors in metadata generation
  }

  const title = !memory
    ? 'Shared Conversation Not Found'
    : memory?.structured?.title || DEFAULT_TITLE_MEMORY;
  const description = !memory
    ? 'This shared conversation is private or no longer available. Open Omi to capture your own.'
    : markdownToPlainText(memory?.structured?.overview) ||
      'A conversation shared from Omi — open it in the app.';

  const ogUrl = prevData.metadataBase
    ? new URL(`/conversations/${params.id}`, prevData.metadataBase).toString()
    : `${envConfig.WEB_URL}/conversations/${params.id}`;

  return {
    title,
    metadataBase: prevData.metadataBase,
    description,
    robots: {
      follow: true,
      index: true,
    },
    openGraph: {
      ...prevData.openGraph,
      title,
      type: 'website',
      url: ogUrl,
      description,
    },
    other: {
      'apple-itunes-app': 'app-id=6502156163',
      'google-play-app': 'app-id=com.friend.ios',
    },
  };
}

export default async function MemoryPage(props: MemoryPageProps) {
  const searchParams = await props.searchParams;
  const params = await props.params;
  const memoryId = params.id;
  const memory = await getSharedMemory(memoryId);
  if (!memory) {
    notFound();
  }

  const userAgent = (await headers()).get('user-agent') || '';
  const openInOmiHref = getConversationSharePlatformLink(userAgent, memoryId);

  return (
    <div className="font-system-ui min-h-screen bg-gradient-to-b from-[#1a0a1f] via-[#0a0a2f] to-black">
      <div className="absolute inset-0 bg-[radial-gradient(circle_500px_at_50%_200px,rgba(88,28,135,0.2),transparent)]" />
      <section className="relative mx-auto max-w-screen-md px-6 py-16 md:px-12 md:py-24">
        <MemoryHeader />
        <Memory memory={memory} searchParams={searchParams} />
        <SharedConversationInstallCta openInOmiHref={openInOmiHref} />
      </section>
    </div>
  );
}
