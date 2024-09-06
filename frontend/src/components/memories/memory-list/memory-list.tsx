'use client';
import { Hits, Pagination } from 'react-instantsearch';
import MemoryItem from './memory-item';
import { NoResultsBoundary } from './no-results-boundary';

export default function MemoryList() {
  return (
    <div className="mt-12 text-white">
      <div className="flex flex-col gap-10">
        <NoResultsBoundary
          fallback={
            <div className="w-full px-4 text-center">
              <h3 className="text-lg font-semibold md:text-xl">
                Sorry, we can't find any matches to your query!
              </h3>
              <p className="mt-2 text-sm font-extralight md:text-base">
                Try to another search query
              </p>
            </div>
          }
        >
          <Hits hitComponent={MemoryItem} />
          <Pagination className="ais-Pagination mx-auto text-sm" />
        </NoResultsBoundary>
      </div>
    </div>
  );
}
