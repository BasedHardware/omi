import MemoryList from '@/src/components/memories/memory-list/memory-list';
import SearchControls from '@/src/components/memories/memory-list/search-controls/search-controls';
import SidePanel from '@/src/components/memories/side-panel/side-panel';
import SidePanelWrapper from '@/src/components/memories/side-panel/side-panel-wrapper';
import { SearchParamsTypes } from '@/src/types/params.types';
import { Suspense } from 'react';
import LoadingPreview from '@/src/components/memories/side-panel/loading-preview';
import Tendencies from '@/src/components/memories/tendencies';

interface MemoriesPageProps {
  searchParams: SearchParamsTypes;
}

export default function MemoriesPage({ searchParams }: MemoriesPageProps) {
  const previewId = searchParams.previewId;
  return (
    <div className="mx-auto my-10 max-w-screen-md px-4 md:my-28">
      <div className="relative col-span-2 mx-auto flex max-w-screen-md text-white">
        <div>
          <SearchControls />
          <Tendencies />
          <Suspense fallback={<div className="text-white">Loading...</div>}>
            <MemoryList searchParams={searchParams} />
          </Suspense>
          <SidePanelWrapper previewId={previewId}>
            <Suspense fallback={<LoadingPreview />}>
              <SidePanel previewId={previewId} />
            </Suspense>
          </SidePanelWrapper>
        </div>
      </div>
    </div>
  );
}
