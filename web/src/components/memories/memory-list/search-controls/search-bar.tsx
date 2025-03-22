'use client';
import { Xmark } from 'iconoir-react';
import { Fragment } from 'react';
import { SearchBox } from 'react-instantsearch';

export default function SearchBar() {
  const queryHook = (query, search) => {
    console.log({ query, search });
    search(query);
  };
  return (
    <Fragment>
      <SearchBox
        placeholder="Search memories"
        className="relative"
        queryHook={queryHook}
        loadingIconComponent={() => <></>}
        submitIconComponent={() => <></>}
        resetIconComponent={() => (
          <div className="absolute right-3 top-[8px] rounded-full p-1 text-white/60 hover:bg-zinc-800 md:right-4 md:top-[15px]">
            <Xmark className="text-sm" />
          </div>
        )}
      />
    </Fragment>
  );
}
