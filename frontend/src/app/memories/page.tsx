import MemoryList from '@/src/components/memories/memory-list/memory-list';
import SearchControls from '@/src/components/memories/memory-list/search-controls/search-controls';
import SidePanel from '@/src/components/memories/side-panel/side-panel';
import SidePanelWrapper from '@/src/components/memories/side-panel/side-panel-wrapper';
import { SearchParamsTypes } from '@/src/types/params.types';
import { Suspense } from 'react';

interface MemoriesPageProps {
  searchParams: SearchParamsTypes;
}

export default function MemoriesPage({ searchParams }: MemoriesPageProps) {
  const previewId = searchParams.previewId;
  return (
    <div className="mx-auto my-10 max-w-screen-md px-4 text-white md:my-28">
      <SearchControls />
      <Suspense fallback={<div className="text-white">Loading...</div>}>
        <MemoryList />
      </Suspense>
      <SidePanelWrapper previewId={previewId}>
        <Suspense fallback={<div className="text-white">Loading...</div>}>
          <SidePanel previewId={previewId} />
        </Suspense>
      </SidePanelWrapper>
    </div>
  );
}
