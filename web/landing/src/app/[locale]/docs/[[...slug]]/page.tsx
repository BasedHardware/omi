import { notFound } from 'next/navigation';
import { DocsContent } from '@/components/docs-content';
import { getDocSlugs, getDocBySlug } from '@/lib/docs-data';

interface Props {
  params: { slug?: string[]; locale: string };
}

export function generateStaticParams() {
  const slugs = getDocSlugs();
  return [{ slug: [] }, ...slugs.map((s) => ({ slug: [s] }))];
}

export default function DocsPage({ params }: Props) {
  const slug = params.slug?.[0];

  // Landing page — show introduction
  if (!slug) {
    const intro = getDocBySlug('introduction');
    if (intro) {
      return <DocsContent docSlug="introduction" />;
    }
  }

  const doc = slug ? getDocBySlug(slug) : undefined;
  if (!doc) return notFound();

  return <DocsContent docSlug={slug!} />;
}
