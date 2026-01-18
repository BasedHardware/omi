interface JsonLdProps {
  data: Record<string, unknown>;
}

export function JsonLd({ data }: JsonLdProps) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}

interface BreadcrumbItem {
  name: string;
  url: string;
}

export function BreadcrumbJsonLd({ items }: { items: BreadcrumbItem[] }) {
  const data = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: `https://omi.me${item.url}`,
    })),
  };

  return <JsonLd data={data} />;
}

interface SoftwareAppJsonLdProps {
  name: string;
  description: string;
  image: string;
  author: string;
  category: string;
  ratingValue?: number;
  ratingCount?: number;
  price?: number;
  url: string;
}

export function SoftwareAppJsonLd({
  name,
  description,
  image,
  author,
  category,
  ratingValue,
  ratingCount,
  price,
  url,
}: SoftwareAppJsonLdProps) {
  const data: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name,
    description,
    image,
    applicationCategory: category,
    operatingSystem: 'iOS, Android',
    author: {
      '@type': 'Person',
      name: author,
    },
    offers: {
      '@type': 'Offer',
      price: price || 0,
      priceCurrency: 'USD',
    },
    url: `https://omi.me${url}`,
  };

  if (ratingValue && ratingCount && ratingCount > 0) {
    data.aggregateRating = {
      '@type': 'AggregateRating',
      ratingValue: ratingValue.toFixed(1),
      ratingCount,
      bestRating: 5,
      worstRating: 1,
    };
  }

  return <JsonLd data={data} />;
}

interface CollectionPageJsonLdProps {
  name: string;
  description: string;
  url: string;
}

export function CollectionPageJsonLd({ name, description, url }: CollectionPageJsonLdProps) {
  const data = {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name,
    description,
    url: `https://omi.me${url}`,
    isPartOf: {
      '@type': 'WebSite',
      name: 'Omi',
      url: 'https://omi.me',
    },
  };

  return <JsonLd data={data} />;
}
