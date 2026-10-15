import getSharedMemory from '@/src/actions/memories/get-shared-memory';
import getSharedScreenshots from '@/src/actions/memories/get-shared-screenshots';
import Memory from '@/src/components/memories/memory';
import MemoryHeader from '@/src/components/memories/memory-header';
import SharedConversationInstallCta, {
  getConversationSharePlatformLink,
} from '@/src/components/memories/shared-conversation-install-cta';
import ShareInstallBar from '@/src/components/memories/share/share-install-bar';
import ShareThemeBoot from '@/src/components/memories/share/share-theme-boot';
import ShareTopbar from '@/src/components/memories/share/share-topbar';
import { shareFonts } from '@/src/components/memories/share/share-fonts';
import envConfig from '@/src/constants/envConfig';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import { markdownToPlainText } from '@/src/lib/markdown-to-plain-text.mjs';
import { getOmiInstallLink } from '@/src/lib/conversation-share-platform-link.mjs';
import {
  capturePreviewRequest,
  previewAttribution,
} from '@/src/lib/share-preview-analytics.mjs';
import { shareAlternates } from '@/src/lib/shared-export.mjs';
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
  props: { params: Promise<ParamsTypes>; searchParams: Promise<SearchParamsTypes> },
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const params = await props.params;
  const searchParams = await props.searchParams;
  const requestHeaders = await headers();
  const attribution = new URLSearchParams();
  if (typeof searchParams.s === 'string') attribution.set('s', searchParams.s);
  if (typeof searchParams.sid === 'string') attribution.set('sid', searchParams.sid);
  await capturePreviewRequest(
    requestHeaders.get('user-agent') || '',
    'metadata',
    attribution,
  );
  const prevData = (await parent) as Metadata;
  // Same uncached read as the page body. Caching this fetch keeps the title
  // and overview in the document head after the share is revoked.
  const memory = (await getSharedMemory(params.id)) ?? null;

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

  // Per-conversation link preview, served by ./og/route.tsx through the
  // /conversations rewrite.
  const ogImageUrl = new URL(`${ogUrl}/og`);
  const safeAttribution = previewAttribution(attribution);
  if (safeAttribution.s !== 'unknown')
    ogImageUrl.searchParams.set('s', safeAttribution.s);
  if (safeAttribution.share_id)
    ogImageUrl.searchParams.set('sid', safeAttribution.share_id);
  const ogImage = {
    url: ogImageUrl.toString(),
    width: 1200,
    height: 630,
    alt: title,
  };

  return {
    title,
    alternates: {
      types: {
        'text/markdown': shareAlternates(params.id).markdown,
        'application/json': shareAlternates(params.id).json,
      },
    },
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
      images: [ogImage],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [ogImage],
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
  // Screenshots are fetched per request, never cached: their signed URLs
  // expire after 60 minutes (see get-shared-screenshots).
  const [memory, screenshots] = await Promise.all([
    getSharedMemory(memoryId),
    getSharedScreenshots(memoryId),
  ]);
  if (!memory) {
    notFound();
  }

  const userAgent = (await headers()).get('user-agent') || '';
  const openInOmiHref = getConversationSharePlatformLink(userAgent, memoryId);
  const installHref = getOmiInstallLink(userAgent);

  return (
    <>
      <ShareThemeBoot />
      <div className={`share-note ${shareFonts}`}>
        <ShareTopbar installHref={installHref} />
        <section className="sn-page">
          <MemoryHeader />
          <Memory memory={memory} searchParams={searchParams} screenshots={screenshots} />
          <SharedConversationInstallCta openInOmiHref={openInOmiHref} />
          <p className="sn-footer">Captured and summarized by Omi</p>
        </section>
        <ShareInstallBar installHref={installHref} />
      </div>
    </>
  );
}
