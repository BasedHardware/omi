import MemoryList from '@/src/components/memories/memory-list/memory-list';
import SearchControls from '@/src/components/memories/memory-list/search-controls/search-controls';
import { Suspense } from 'react';

export default function MemoriesPage() {
  return(
    <div className='text-white md:my-28 my-10 max-w-screen-md mx-auto'>
      <SearchControls/>
      <Suspense fallback={
        <div className='text-white'>
          Loading...
        </div>
      }>
        <MemoryList />
      </Suspense>
    </div>
  )
}
