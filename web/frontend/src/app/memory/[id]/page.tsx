import type { Metadata } from 'next';
import { ItemLinkFallback } from '@/src/components/item-link/item-link-fallback';
import { ITEM_LINK_METADATA } from '@/src/lib/item-link.mjs';

// Private item link fallback. Never fetch the memory here: see item-link.mjs.
export const metadata: Metadata = ITEM_LINK_METADATA as Metadata;

export default async function MemoryItemLinkPage(props: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await props.params;
  return <ItemLinkFallback kind="memory" id={id} />;
}
