import SearchControls from '@/src/components/memories/memory-list/search-controls/search-controls';
import { SearchParamsTypes } from '@/src/types/params.types';
import { Fragment, Suspense } from 'react';
import LoadingPreview from '@/src/components/memories/side-panel/loading-preview';
import Tendencies from '@/src/components/memories/tendencies';
import { Metadata } from 'next';
import SidePanelWrapper from '@/src/components/memories/side-panel/side-panel-wrapper';
import SidePanel from '@/src/components/memories/side-panel/side-panel';
import MemoryList from '@/src/components/memories/memory-list/memory-list';
import SearchBar from '@/src/components/memories/memory-list/search-controls/search-bar';
import './styles.css';
import TrendingBanner from '@/src/components/memories/tendencies/trending-banner';

interface MemoriesPageProps {
  searchParams: SearchParamsTypes;
}

export const metadata: Metadata = {
  title: 'Community Memories',
  description:
    'Relive the moments that matter, discover new stories, and connect with others through our shared community memories.',
};

export default function MemoriesPage({ searchParams }: MemoriesPageProps) {
  const previewId = searchParams.previewId;
  return (
    <Fragment>
      <TrendingBanner />
      <div className="my-44 flex w-full px-4">
        <div className="mx-auto w-full max-w-screen-xl">
          <h1 className="text-center text-3xl font-bold text-white md:text-start md:text-4xl">
            Memories
          </h1>
          <SearchControls>
            <div className="mt-10 flex w-full items-start gap-10">
              <div className="w-full">
                <SearchBar />
                <MemoryList />
              </div>
              <Tendencies />
            </div>
          </SearchControls>
        </div>
        <SidePanelWrapper previewId={previewId}>
          <Suspense fallback={<LoadingPreview />}>
            <SidePanel previewId={previewId} />
          </Suspense>
        </SidePanelWrapper>
      </div>
    </Fragment>
  );
}
