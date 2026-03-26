import { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';
import { PrivacyContent } from './privacy-content';

export async function generateMetadata({ params }: { params: { locale: string } }): Promise<Metadata> {
  const t = await getTranslations({ locale: params.locale, namespace: 'metadata' });
  return {
    title: t('privacyTitle'),
    description: t('privacyDescription'),
  };
}

export default function PrivacyPage() {
  return <PrivacyContent />;
}
