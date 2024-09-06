'use client';
import { SearchBox } from 'react-instantsearch';

export default function SearchBar() {
  return (
    <SearchBox
      placeholder="Search memories"
      loadingIconComponent={() => <></>}
      submitIconComponent={() => <></>}
      resetIconComponent={() => <></>}
    />
  );
}
