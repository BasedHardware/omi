'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';

export default function SearchBar() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const searchValue = searchParams.get('search') || '';

  const handleSearch = (category: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('search', category);
    router.push(`${pathname}?${params.toString()}`);
  };

  return (
    <input
      type="text"
      defaultValue={searchValue}
      placeholder="Search memories"
      onChange={(e) => handleSearch(e.target.value)}
      className="w-full rounded-md border border-solid border-zinc-600 bg-transparent px-3 py-2"
    />
  );
}
