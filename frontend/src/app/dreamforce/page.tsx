import DreamforceHeader from '@/src/components/dreamforce/dreamforce-header';
import GetTrendsMainPage from '@/src/components/trends/get-trends-main-page';
import TrendsTitle from '@/src/components/trends/trends-title';
import { Trend } from '@/src/types/trends/trends.types';
import { Fragment, Suspense } from 'react';

const trendMock: Trend[] = [
  {
    create_at: new Date(),
    category: 'Dreamforce',
    id: '1',
    topics: [
      {
        id: '1',
        topic: 'Salesforce',
        memories_count: 100,
      },
      {
        id: '2',
        topic: 'Trailhead',
        memories_count: 50,
      },
      {
        id: '3',
        topic: 'Dreamforce',
        memories_count: 10,
      },
    ],
  },
  {
    create_at: new Date(),
    category: 'Investment',
    id: '2',
    topics: [
      {
        id: '1',
        topic: 'Investors',
        memories_count: 4,
      },
      {
        id: '2',
        topic: 'Trailhead',
        memories_count: 32,
      },
    ],
  },
];

export default function DreamforcePage() {
  return (
    <Fragment>
        <DreamforceHeader />
      <div className="flex min-h-screen w-full bg-gradient-to-t from-[#d2e3ff] via-white via-55% to-white px-4">
        <div className="mx-auto my-44 w-full max-w-screen-xl">
          <TrendsTitle>
            <Suspense fallback={null}>
              <GetTrendsMainPage />
            </Suspense>
          </TrendsTitle>
        </div>
      </div>
    </Fragment>
  );
}
