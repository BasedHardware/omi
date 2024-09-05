import SearchControls from '@/src/components/memories/memory-list/search-controls/search-controls';
import { SearchParamsTypes } from '@/src/types/params.types';
import { Suspense } from 'react';
import LoadingPreview from '@/src/components/memories/side-panel/loading-preview';
import Tendencies from '@/src/components/memories/tendencies';
import { Metadata } from 'next';
import SidePanelWrapper from '@/src/components/memories/side-panel/side-panel-wrapper';
import SidePanel from '@/src/components/memories/side-panel/side-panel';
import MemoryList from '@/src/components/memories/memory-list/memory-list';
import './styles.css';

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
    <div className="mx-auto my-10 max-w-screen-md px-4 md:my-28">
      <div className="relative col-span-2 mx-auto flex max-w-screen-md text-white">
        <div className="w-full">
          <SearchControls>
            <Tendencies />
            <MemoryList searchParams={searchParams} />
          </SearchControls>
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

// export const Hit = ({ hit }) => {
//   return (
//     <article>
//       <img src={hit.backdrop_path} />
// 			<div className="hit-original_title">
// 			  <Highlight attribute="original_title" hit={hit} />
// 			</div>
// 			<div className="hit-overview">
// 			  <Highlight attribute="overview" hit={hit} />
// 			</div>
// 			<div className="hit-release_date">
// 			  <Highlight attribute="release_date" hit={hit} />
// 			</div>
//     </article>
//   );
// };
