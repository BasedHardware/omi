import getSharedMemory from '@/src/actions/memories/get-shared-memory';
import Memory from '@/src/components/memories/memory';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import { ParamsTypes, SearchParamsTypes } from '@/src/types/params.types';
import { Metadata, ResolvingMetadata } from 'next';

export async function generateMetadata(
  { params }: { params: ParamsTypes },
  parent: ResolvingMetadata,
): Promise<Metadata> {
  // read route params
  const prevData = (await parent) as Metadata;
  const memory = await getSharedMemory(params.id);

  const title = !memory ? 'Memory Not Found' : memory.structured.title || DEFAULT_TITLE_MEMORY;

  return {
    title: title,
    metadataBase: prevData.metadataBase,
    description: prevData.description,
    robots: {
      follow: true,
      index: true,
    },
    twitter: {
      card: 'summary_large_image',
    },
    openGraph: {
      title: title,
      url: `${prevData.metadataBase}/memories/${params.id}`,
      type: 'website',
      description: prevData.openGraph?.description,
    },
  };
}

interface MemoryPageProps {
  params: ParamsTypes;
  searchParams: SearchParamsTypes;
}

export default async function MemoryPage({ params, searchParams }: MemoryPageProps) {
  const memoryId = params.id;
  const memory = await getSharedMemory(memoryId);
  if (!memory) throw new Error();
  return <Memory memory={memory} searchParams={searchParams} />;
}
