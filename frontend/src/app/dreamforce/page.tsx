import DreamforceHeader from '@/src/components/dreamforce/dreamforce-header';
import TrendsError from '@/src/components/dreamforce/trends-error';
import GetTrendsMainPage from '@/src/components/trends/get-trends-main-page';
import TrendsTitle from '@/src/components/trends/trends-title';
import { ErrorBoundary } from 'next/dist/client/components/error-boundary';
import { Fragment, Suspense } from 'react';

export default function DreamforcePage() {
  return (
    <Fragment>
      <DreamforceHeader />
      <div className="flex min-h-screen w-full bg-gradient-to-t from-[#d2e3ff] via-white via-55% to-white px-4">
        <div className="mx-auto my-44 w-full max-w-screen-xl">
          <TrendsTitle>
            <ErrorBoundary errorComponent={TrendsError}>
              <Suspense fallback={<></>}>
                <GetTrendsMainPage />
              </Suspense>
            </ErrorBoundary>
          </TrendsTitle>
        </div>
      </div>
    </Fragment>
  );
}
