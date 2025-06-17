import DreamforceHeader from '@/src/components/dreamforce/dreamforce-header';
import TrendsError from '@/src/components/dreamforce/trends-error';
import GetTrendsMainPage from '@/src/components/trends/get-trends-main-page';
import TrendsTitle from '@/src/components/trends/trends-title';
import { OnePointCircle } from 'iconoir-react';
import { ErrorBoundary } from 'next/dist/client/components/error-boundary';
import Image from 'next/image';
import { Fragment, Suspense } from 'react';

export default function DreamforcePage() {
  return (
    <Fragment>
      <DreamforceHeader />
      <div className="flex min-h-screen w-full bg-gradient-to-t from-[#d2e3ff] via-white via-55% to-white px-4">
        <div className="mx-auto my-44 w-full max-w-screen-xl">
          <Image
            src={'/df-sf.png'}
            alt="Dreamforce Banner"
            width={1920}
            height={1080}
            className=" mx-auto mb-10 h-[10rem] w-full rounded-3xl bg-cover object-cover md:h-[20rem] md:w-[80%]"
          />
          <TrendsTitle>
            <ErrorBoundary errorComponent={TrendsError}>
              <Suspense
                fallback={
                  <div className="mx-auto mt-20 max-w-screen-md space-y-8">
                    <p className="text-center text-lg text-gray-500">
                      We are loading the trends for you. Please wait a moment.
                    </p>
                    <OnePointCircle className="mx-auto animate-spin text-xl text-gray-500" />
                  </div>
                }
              >
                <GetTrendsMainPage />
              </Suspense>
            </ErrorBoundary>
          </TrendsTitle>
        </div>
      </div>
    </Fragment>
  );
}
