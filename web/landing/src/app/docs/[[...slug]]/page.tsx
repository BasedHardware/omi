import { notFound } from 'next/navigation';
import { DocsContent } from '@/components/docs-content';
import { findDocBySlug, getAllSlugs, docsNav } from '@/lib/docs-nav';

interface Props {
  params: { slug?: string[] };
}

export function generateStaticParams() {
  return [{ slug: [] }, ...getAllSlugs().map((s) => ({ slug: [s] }))];
}

export default function DocsPage({ params }: Props) {
  const slug = params.slug?.[0];

  // Landing page — show introduction
  if (!slug) {
    const intro = findDocBySlug('introduction');
    if (intro) {
      return <DocsContent title={intro.title} description={intro.description} content={intro.content} />;
    }
  }

  const doc = slug ? findDocBySlug(slug) : undefined;
  if (!doc) return notFound();

  return <DocsContent title={doc.title} description={doc.description} content={doc.content} />;
}
