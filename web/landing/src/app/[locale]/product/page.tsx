import { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';
import { ProductContent } from './product-content';

export async function generateMetadata({ params }: { params: { locale: string } }): Promise<Metadata> {
  const t = await getTranslations({ locale: params.locale, namespace: 'metadata' });
  return {
    title: t('productTitle'),
    description: t('productDescription'),
  };
}

export default function ProductPage() {
  return <ProductContent />;
}
