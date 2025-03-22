import { SearchParamsTypes } from '@/src/types/params.types';
import { Metadata } from 'next';
import './styles.css';
import { redirect } from 'next/navigation';

interface MemoriesPageProps {
  searchParams: SearchParamsTypes;
}

export const metadata: Metadata = {
  title: 'Community Memories',
  description:
    'Relive the moments that matter, discover new stories, and connect with others through our shared community memories.',
};

export default function MemoriesPage({ searchParams }: MemoriesPageProps) {
  redirect('/dreamforce');
  // const previewId = searchParams.previewId;
  // return (
  //   <Fragment>
  //     {/* <TrendingBanner /> */}
  //     <div className="my-44 flex w-full px-4">
  //       <div className="mx-auto w-full max-w-screen-xl">
  //         <h1 className="text-center text-3xl font-bold text-white md:text-start md:text-4xl">
  //           Memories
  //         </h1>
  //         <SearchControls>
  //           <div className="mt-10 flex w-full items-start gap-10">
  //             <div className="w-full">
  //               <SearchBar />
  //               <MemoryList />
  //             </div>
  //             <Tendencies />
  //           </div>
  //         </SearchControls>
  //       </div>
  //       <SidePanelWrapper previewId={previewId}>
  //         <Suspense fallback={<LoadingPreview />}>
  //           <SidePanel previewId={previewId} />
  //         </Suspense>
  //       </SidePanelWrapper>
  //     </div>
  //   </Fragment>
  // );
}
