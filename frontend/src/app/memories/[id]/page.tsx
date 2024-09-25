import getSharedMemory from '@/src/actions/memories/get-shared-memory';
import Memory from '@/src/components/memories/memory';
import MemoryHeader from '@/src/components/memories/memory-header';
import envConfig from '@/src/constants/envConfig';
import { DEFAULT_TITLE_MEMORY } from '@/src/constants/memory';
import { ParamsTypes, SearchParamsTypes } from '@/src/types/params.types';
import { Metadata, ResolvingMetadata } from 'next';

interface MemoryPageProps {
  params: ParamsTypes;
  searchParams: SearchParamsTypes;
}

export async function generateMetadata(
  { params }: { params: ParamsTypes },
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const prevData = (await parent) as Metadata;
  const memory = (await (
    await fetch(`${envConfig.API_URL}/v1/memories/${params.id}/shared`, {
      next: {
        revalidate: 60,
      },
    })
  ).json()) as any;

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
  if (!memory) throw new Error();

  return (
    <section className="mx-3 my-10 mt-10 max-w-screen-md md:mx-auto md:my-28">
      <MemoryHeader />
      <Memory memory={memory} searchParams={searchParams} />
    </section>
  );
}
