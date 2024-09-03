import MemoryList from '@/src/components/memories/memory-list/memory-list';
import { Suspense } from 'react';

export default function MemoriesPage() {
  return(
    <Suspense fallback={
      <div className='text-white'>
        Loading...
      </div>
    }>
      <MemoryList />
    </Suspense>
  )
}
