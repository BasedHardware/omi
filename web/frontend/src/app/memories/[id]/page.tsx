import getSharedMemory from '@/src/actions/memories/get-shared-memory';
import Memory from '@/src/components/memories/memory';
import MemoryHeader from '@/src/components/memories/memory-header';
import envConfig from '@/src/constants/envConfig';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import { ParamsTypes, SearchParamsTypes } from '@/src/types/params.types';
import { Metadata, ResolvingMetadata } from 'next';
import { notFound } from 'next/navigation';

interface MemoryPageProps {
  params: ParamsTypes;
  searchParams: SearchParamsTypes;
}

export async function generateMetadata(
  { params }: { params: ParamsTypes },
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const prevData = (await parent) as Metadata;
  let memory: { structured?: { title?: string; overview?: string } } | null = null;
  
  try {
    const response = await fetch(`${envConfig.API_URL}/v1/conversations/${params.id}/shared`, {
      next: {
        revalidate: 60,
      },
    });
    
    if (response.ok) {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        memory = await response.json();
      }
    }
  } catch (error) {
    // Silently handle errors in metadata generation
  }

  const title = !memory
    ? 'Memory Not Found'
    : memory?.structured?.title || DEFAULT_TITLE_MEMORY;

  return {
    title: title,
    metadataBase: prevData.metadataBase,
    description: prevData.description,
    robots: {
      follow: true,
      index: true,
    },
    openGraph: {
      ...prevData.openGraph,
      title: title,
      type: 'website',
      url: `${prevData.metadataBase}/memories/${params.id}`,
      description: memory?.structured?.overview || prevData.openGraph?.description,
    },
  };
}

export default async function MemoryPage({ params, searchParams }: MemoryPageProps) {
  const memoryId = params.id;
  const memory = await getSharedMemory(memoryId);
  if (!memory) {
    notFound();
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#1a0a1f] via-[#0a0a2f] to-black font-system-ui">
      <div className="absolute inset-0 bg-[radial-gradient(circle_500px_at_50%_200px,rgba(88,28,135,0.2),transparent)]" />
      <section className="relative mx-auto max-w-screen-md px-6 py-16 md:px-12 md:py-24">
        <MemoryHeader />
        <Memory memory={memory} searchParams={searchParams} />
      </section>
    </div>
  );
}
