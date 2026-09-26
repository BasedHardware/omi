import getSharedMemory from '@/src/actions/memories/get-shared-memory';
import Memory from '@/src/components/memories/memory';
import MemoryHeader from '@/src/components/memories/memory-header';
import SharedConversationInstallCta, {
  getConversationSharePlatformLink,
} from '@/src/components/memories/shared-conversation-install-cta';
import envConfig from '@/src/constants/envConfig';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import { markdownToPlainText } from '@/src/lib/markdown-to-plain-text.mjs';
import { sharedApiUrl } from '@/src/lib/shared-api-url.mjs';
import { firstSectionBulletPlainText } from '@/src/lib/shared-note.mjs';
import { ParamsTypes, SearchParamsTypes } from '@/src/types/params.types';
import { Metadata, ResolvingMetadata } from 'next';
import { headers } from 'next/headers';
import { notFound } from 'next/navigation';
import './share-note.css';

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
  let memory: {
    structured?: {
      title?: string;
      overview?: string;
      sections?: unknown;
    };
  } | null = null;

  try {
    const response = await fetch(
      sharedApiUrl(envConfig.API_URL, 'v1', 'conversations', params.id, 'shared'),
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
    : firstSectionBulletPlainText(memory?.structured?.sections) ||
      markdownToPlainText(memory?.structured?.overview) ||
      'A conversation shared from Omi — open it in the app.';

  const ogUrl = prevData.metadataBase
    ? new URL(
        `/conversations/${encodeURIComponent(params.id)}`,
        prevData.metadataBase,
      ).toString()
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
    <div className="share-note">
      <section className="sn-page">
        <MemoryHeader />
        <Memory memory={memory} searchParams={searchParams} />
        <SharedConversationInstallCta openInOmiHref={openInOmiHref} />
      </section>
    </div>
  );
}
