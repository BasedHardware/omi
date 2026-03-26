'use client';

import {
  Database,
  SlidersHorizontal,
  ShieldCheck,
  Wand2,
  Bell,
  FlaskConical,
  Server,
  Lock,
  Handshake,
  Scale,
  PenLine,
  ToggleRight,
  Trash2,
  Info,
  Mail,
  TriangleAlert,
  FileText,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Navbar } from '@/components/navbar';
import { Footer } from '@/components/footer';
import { InfoCard, InfoCardGroup } from '@/components/ui/info-card';
import { AccordionItem, AccordionGroup } from '@/components/ui/accordion';
import { brand } from '@/lib/config';

export function PrivacyContent() {
  const t = useTranslations('privacy');

  return (
    <>
      <Navbar />
      <main className="pt-28 pb-20">
        <div className="mx-auto max-w-3xl px-6">
          {/* Header */}
          <div className="mb-16">
            <h1 className="font-display font-bold text-4xl md:text-5xl mb-4">{t('title')}</h1>
            <p className="text-text-tertiary text-lg leading-relaxed">{t('intro')}</p>
          </div>

          {/* Overview */}
          <Section title={t('overviewTitle')}>
            <InfoCardGroup cols={3}>
              <InfoCard icon={Database} title={t('yourData')} description={t('yourDataDesc')} />
              <InfoCard icon={SlidersHorizontal} title={t('yourControl')} description={t('yourControlDesc')} />
              <InfoCard icon={ShieldCheck} title={t('yourSecurity')} description={t('yourSecurityDesc')} />
            </InfoCardGroup>
          </Section>

          {/* 1. Information We Collect */}
          <Section title={t('infoCollectTitle')}>
            <AccordionGroup>
              <AccordionItem title={t('personalInfo')} icon={PenLine} defaultOpen>
                {t('personalInfoDesc')}
              </AccordionItem>
              <AccordionItem title={t('conversationalData')} icon={Bell}>
                {t('conversationalDataDesc')}
              </AccordionItem>
              <AccordionItem title={t('usageData')} icon={SlidersHorizontal}>
                {t('usageDataDesc')}
              </AccordionItem>
            </AccordionGroup>
          </Section>

          {/* 2. Purpose of Information Use */}
          <Section title={t('infoUseTitle')}>
            <p className="text-text-tertiary text-sm mb-6">{t('infoUseIntro')}</p>
            <InfoCardGroup cols={3}>
              <InfoCard icon={Wand2} title={t('serviceEnhancement')} description={t('serviceEnhancementDesc')} />
              <InfoCard icon={Bell} title={t('userCommunication')} description={t('userCommunicationDesc')} />
              <InfoCard icon={FlaskConical} title={t('innovationResearch')} description={t('innovationResearchDesc')} />
            </InfoCardGroup>
          </Section>

          {/* 3. Data Storage and Security */}
          <Section title={t('dataStorageTitle')}>
            <InfoCardGroup cols={2}>
              <InfoCard icon={Server} title={t('robustStorage')} description={t('robustStorageDesc')} />
              <InfoCard icon={Lock} title={t('uncomprSecurity')} description={t('uncomprSecurityDesc')} />
            </InfoCardGroup>
          </Section>

          {/* 4. Information Sharing */}
          <Section title={t('infoSharingTitle')}>
            <AccordionGroup>
              <AccordionItem title={t('selectiveSharing')} icon={Handshake}>
                {t('selectiveSharingDesc')}
              </AccordionItem>
              <AccordionItem title={t('legalCompliance')} icon={Scale}>
                {t('legalComplianceDesc')}
              </AccordionItem>
            </AccordionGroup>
          </Section>

          {/* 5. Your Privacy Rights */}
          <Section title={t('privacyRightsTitle')}>
            <p className="text-text-tertiary text-sm mb-6">{t('privacyRightsIntro')}</p>
            <InfoCardGroup cols={3}>
              <InfoCard icon={PenLine} title={t('accessUpdate')} description={t('accessUpdateDesc')} />
              <InfoCard icon={ToggleRight} title={t('chooseDataUse')} description={t('chooseDataUseDesc')} />
              <InfoCard icon={Trash2} title={t('dataDeletion')} description={t('dataDeletionDesc')} />
            </InfoCardGroup>
          </Section>

          {/* 6. Wearable App Version */}
          <Section title={t('wearableTitle')}>
            <div className="rounded-2xl border border-brand/20 bg-brand/5 p-6">
              <div className="flex items-start gap-3">
                <Info size={20} className="text-brand flex-shrink-0 mt-0.5" />
                <p
                  className="text-text-secondary text-sm leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: t('wearableDesc') }}
                />
              </div>
            </div>
          </Section>

          {/* 7. Policy Updates */}
          <Section title={t('policyUpdatesTitle')}>
            <div className="rounded-2xl border border-yellow-500/20 bg-yellow-500/5 p-6">
              <div className="flex items-start gap-3">
                <TriangleAlert size={20} className="text-yellow-500 flex-shrink-0 mt-0.5" />
                <p className="text-text-secondary text-sm leading-relaxed">{t('policyUpdatesDesc')}</p>
              </div>
            </div>
          </Section>

          {/* 8. Contact Us */}
          <Section title={t('contactTitle')}>
            <InfoCard
              icon={Mail}
              title={t('contactCardTitle')}
              description={t('contactCardDesc', { email: brand.email })}
              href={`mailto:${brand.email}`}
            />
          </Section>

          {/* Related */}
          <Section title={t('relatedTitle')}>
            <InfoCardGroup cols={2}>
              <InfoCard icon={TriangleAlert} title={t('disclaimer')} description={t('disclaimerDesc')} href="/docs/disclaimer" />
              <InfoCard icon={FileText} title={t('license')} description={t('licenseDesc')} href="/docs/license" />
            </InfoCardGroup>
          </Section>
        </div>
      </main>
      <Footer />
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-14">
      <h2 className="font-display font-bold text-xl md:text-2xl mb-6">{title}</h2>
      {children}
    </section>
  );
}
