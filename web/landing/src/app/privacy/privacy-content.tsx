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
import { Navbar } from '@/components/navbar';
import { Footer } from '@/components/footer';
import { InfoCard, InfoCardGroup } from '@/components/ui/info-card';
import { AccordionItem, AccordionGroup } from '@/components/ui/accordion';
import { brand } from '@/lib/config';

export function PrivacyContent() {
  return (
    <>
      <Navbar />
      <main className="pt-28 pb-20">
        <div className="mx-auto max-w-3xl px-6">
          {/* Header */}
          <div className="mb-16">
            <h1 className="font-display font-bold text-4xl md:text-5xl mb-4">Privacy Policy</h1>
            <p className="text-text-tertiary text-lg leading-relaxed">
              At {brand.name}, your privacy and the security of your data are our top priorities. This Privacy Policy
              explains how we collect, use, and protect your information.
            </p>
          </div>

          {/* Overview */}
          <Section title="Overview">
            <InfoCardGroup cols={3}>
              <InfoCard icon={Database} title="Your Data" description="We only collect what's necessary to provide and improve our services." />
              <InfoCard icon={SlidersHorizontal} title="Your Control" description="You decide how your data is used and can manage your preferences at any time." />
              <InfoCard icon={ShieldCheck} title="Your Security" description="Advanced encryption and security protocols protect your information." />
            </InfoCardGroup>
          </Section>

          {/* 1. Information We Collect */}
          <Section title="1. Information We Collect">
            <AccordionGroup>
              <AccordionItem title="Personal Information" icon={PenLine} defaultOpen>
                Includes your name, email, and contact details, necessary for account creation and management.
              </AccordionItem>
              <AccordionItem title="Conversational Data" icon={Bell}>
                We record and store your conversations to offer tailored AI feedback and enrich your personal memory
                bank. Audio data is processed to generate transcripts, summaries, and action items.
              </AccordionItem>
              <AccordionItem title="Usage Data" icon={SlidersHorizontal}>
                Insights into how you interact with our app, like feature usage and session duration, are used for
                continuous improvement of our services.
              </AccordionItem>
            </AccordionGroup>
          </Section>

          {/* 2. Purpose of Information Use */}
          <Section title="2. Purpose of Information Use">
            <p className="text-text-tertiary text-sm mb-6">We are dedicated to using your information responsibly:</p>
            <InfoCardGroup cols={3}>
              <InfoCard
                icon={Wand2}
                title="Service Enhancement"
                description="To offer state-of-the-art conversation recording, AI-driven analysis, and efficient memory bank services."
              />
              <InfoCard
                icon={Bell}
                title="User Communication"
                description="For updates, support, and promotional content (with your consent)."
              />
              <InfoCard
                icon={FlaskConical}
                title="Innovation & Research"
                description="Continuously researching and analyzing data to improve functionality."
              />
            </InfoCardGroup>
          </Section>

          {/* 3. Data Storage and Security */}
          <Section title="3. Data Storage and Security">
            <InfoCardGroup cols={2}>
              <InfoCard
                icon={Server}
                title="Robust Storage Solutions"
                description="Your data is stored on highly secure servers, safeguarded with advanced technology and regular security audits."
              />
              <InfoCard
                icon={Lock}
                title="Uncompromised Security"
                description="We employ the latest security protocols including end-to-end encryption to prevent data breaches and protect against unauthorized access."
              />
            </InfoCardGroup>
          </Section>

          {/* 4. Information Sharing */}
          <Section title="4. Information Sharing">
            <AccordionGroup>
              <AccordionItem title="Selective Sharing with Service Providers" icon={Handshake}>
                We collaborate with third-party providers under stringent confidentiality agreements, ensuring they
                adhere to our privacy standards. These providers assist with hosting, analytics, and AI processing.
              </AccordionItem>
              <AccordionItem title="Compliance with Legal Obligations" icon={Scale}>
                We may disclose your information if required by law, always respecting your privacy rights and notifying
                you when legally permitted.
              </AccordionItem>
            </AccordionGroup>
          </Section>

          {/* 5. Your Privacy Rights */}
          <Section title="5. Your Privacy Rights">
            <p className="text-text-tertiary text-sm mb-6">You are empowered to:</p>
            <InfoCardGroup cols={3}>
              <InfoCard
                icon={PenLine}
                title="Access & Update"
                description="View and modify your personal information at any time through your account settings."
              />
              <InfoCard
                icon={ToggleRight}
                title="Choose Your Data Use"
                description="Opt out of non-essential data uses, like marketing communications and analytics."
              />
              <InfoCard
                icon={Trash2}
                title="Data Deletion"
                description="Request the complete removal of your data, within legal and operational requirements."
              />
            </InfoCardGroup>
          </Section>

          {/* 6. Wearable App Version */}
          <Section title="6. Wearable App Version">
            <div className="rounded-2xl border border-brand/20 bg-brand/5 p-6">
              <div className="flex items-start gap-3">
                <Info size={20} className="text-brand flex-shrink-0 mt-0.5" />
                <p className="text-text-secondary text-sm leading-relaxed">
                  We offer an alternative version of our app that integrates with wearable devices. In this version,{' '}
                  <strong className="text-white">no data is collected by {brand.name}</strong>. You bring your own API
                  keys, and all data is stored locally on your device. This ensures complete control over your data and
                  privacy.
                </p>
              </div>
            </div>
          </Section>

          {/* 7. Policy Updates */}
          <Section title="7. Policy Updates">
            <div className="rounded-2xl border border-yellow-500/20 bg-yellow-500/5 p-6">
              <div className="flex items-start gap-3">
                <TriangleAlert size={20} className="text-yellow-500 flex-shrink-0 mt-0.5" />
                <p className="text-text-secondary text-sm leading-relaxed">
                  We reserve the right to modify this policy. Changes will be communicated transparently on this page,
                  along with the revision date. We encourage you to review this policy periodically.
                </p>
              </div>
            </div>
          </Section>

          {/* 8. Contact Us */}
          <Section title="8. Contact Us">
            <InfoCard
              icon={Mail}
              title="Questions or Concerns?"
              description={`For any inquiries regarding our data practices or this policy, please contact us at ${brand.email}`}
              href={`mailto:${brand.email}`}
            />
          </Section>

          {/* Related */}
          <Section title="Related">
            <InfoCardGroup cols={2}>
              <InfoCard icon={TriangleAlert} title="Disclaimer" description="Important usage information." href="/docs/disclaimer" />
              <InfoCard icon={FileText} title="License" description="MIT License details." href="/docs/license" />
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
