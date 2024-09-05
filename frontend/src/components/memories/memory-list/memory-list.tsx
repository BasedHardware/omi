'use client';
import { Hits, Pagination} from 'react-instantsearch';
import { SearchParamsTypes } from '@/src/types/params.types';
import MemoryItem from './memory-item';

interface MemoryListProps {
  searchParams: SearchParamsTypes;
}

export default function MemoryList({ searchParams }: MemoryListProps) {
  return (
    <div className="mt-12 text-white">
      <div className="flex flex-col gap-10">
        <Hits hitComponent={MemoryItem} />
        <Pagination className='ais-Pagination mx-auto text-sm'/>
      </div>
    </div>
  );
}
