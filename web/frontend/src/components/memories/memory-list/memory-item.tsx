import { Hit } from 'algoliasearch';
import moment from 'moment';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Highlight } from 'react-instantsearch';

interface MemoryItemProps {
  hit: Hit;
}

export default function MemoryItem({ hit }: MemoryItemProps) {
  const searchParams = useSearchParams();
  return (
    <Link
      href={`/memories?${searchParams.toString()}&previewId=${hit.id}`}
      className="group flex w-full items-start gap-4 border-b border-solid border-gray-700 pb-8 last:border-transparent md:gap-7"
    >
      <div className="w-fit rounded-md bg-zinc-800 p-2.5 text-sm transition-colors group-hover:bg-zinc-700 md:p-4 md:text-base">
        {hit.structured?.emoji}
      </div>
      <div>
        <h2 className="line-clamp-2 text-base font-semibold group-hover:underline md:text-xl">
          {!hit?.structured?.title ? (
            'Untitle memory'
          ) : (
            <Highlight attribute="structured.title" hit={hit} />
          )}
        </h2>
        <div className="line-clamp-2 text-sm font-extralight text-zinc-300 md:text-base">
          {!hit?.structured?.overview ? (
            "This memory doesn't have an overview"
          ) : (
            <Highlight attribute="structured.overview" hit={hit} />
          )}
        </div>
        <div className="mt-8 flex items-center justify-start gap-1.5 text-xs text-zinc-400 md:text-sm">
          <p>{moment(hit.created_at).format('MMM Do YYYY')}</p>
          <div className="text-xs">•</div>
          <p className="rounded-full">
            <Highlight attribute={'structured.category'} hit={hit} />
          </p>
        </div>
      </div>
    </Link>
  );
}
