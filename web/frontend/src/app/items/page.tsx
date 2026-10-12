import type { Metadata } from 'next';
import { headers } from 'next/headers';
import { ItemListLinkFallback } from '@/src/components/item-link/item-link-fallback';
import {
  ITEM_LIST_QUERY_HEADER,
  itemListFromSearchParams,
  itemListMetadata,
  parseItemListQuery,
} from '@/src/lib/item-link.mjs';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

// Private item list fallback. Never fetch the items here: see item-link.mjs.
// The proxy passes the raw query so the list keeps the URL's order.
async function itemsFor(searchParams: SearchParams) {
  const raw = (await headers()).get(ITEM_LIST_QUERY_HEADER);
  return raw !== null
    ? parseItemListQuery(raw)
    : itemListFromSearchParams(await searchParams);
}

export async function generateMetadata(props: {
  searchParams: SearchParams;
}): Promise<Metadata> {
  // Count only: nothing about the items themselves reaches a link preview.
  return itemListMetadata((await itemsFor(props.searchParams)).length) as Metadata;
}

export default async function ItemListLinkPage(props: { searchParams: SearchParams }) {
  return <ItemListLinkFallback items={await itemsFor(props.searchParams)} />;
}
