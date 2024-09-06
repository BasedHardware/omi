'use client';
import { Xmark } from 'iconoir-react';
import { SearchBox } from 'react-instantsearch';

export default function SearchBar() {
  return (
    <SearchBox
      placeholder="Search memories"
      className='relative'
      loadingIconComponent={() => <></>}
      submitIconComponent={() => <></>}
      resetIconComponent={() => (
        <div className='absolute top-[8px] md:top-[15px] right-3 md:right-4 text-white/60 p-1 hover:bg-zinc-800 rounded-full'>
          <Xmark className='text-sm'/>
        </div>
      )}
    />
  );
}
