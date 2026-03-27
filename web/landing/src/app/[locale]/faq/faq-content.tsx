'use client';

import { useRef, useEffect, useState } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ChevronDown, Mail } from 'lucide-react';
import { Link } from '@/i18n/navigation';
import { Navbar } from '@/components/navbar';
import { Footer } from '@/components/footer';
import { brand } from '@/lib/config';

gsap.registerPlugin(ScrollTrigger);

interface FaqItem {
  q: string;
  a: string;
}

interface FaqGroup {
  title: string;
  items: FaqItem[];
}

const faqGroups: FaqGroup[] = [
  {
    title: 'General',
    items: [
      {
        q: `What is ${brand.name}?`,
        a: `${brand.name} is a wearable AI companion that captures your conversations — meetings, brainstorms, calls — and transforms them into structured summaries, action items, and searchable memories. It works across phone, desktop, and all wearables.`,
      },
      {
        q: 'How does it work?',
        a: `Wear or carry ${brand.name} during any conversation. It records audio, transcribes it in real-time using AI, and automatically generates summaries, action items, and memories. Everything syncs across your devices.`,
      },
      {
        q: 'Do I need specific hardware?',
        a: `${brand.name} works with the ${brand.name} pendant, but also with your phone, Mac desktop app, and any web browser. The pendant provides the best hands-free experience, but you can start with just the app.`,
      },
      {
        q: 'What languages are supported?',
        a: `${brand.name} supports 25+ languages including English, Spanish, Portuguese, French, German, Japanese, Chinese, Korean, and more. It handles single-language, multilingual, and real-time translation modes.`,
      },
    ],
  },
  {
    title: 'Product & Hardware',
    items: [
      {
        q: 'What are the technical specifications?',
        a: 'Battery: 150 mAh (10-14 hours). Dimensions: 2.5cm diameter x 1.5cm height. Dual microphones with noise reduction. Bluetooth 5.1 + Wi-Fi (2.4/5 GHz). Magnetic charging dock. Speaker recognition supported.',
      },
      {
        q: "What's included in the box?",
        a: `The ${brand.name} device, protective silicone case, neck lanyard, magnetic charging cable (USB-C), and a quick start guide.`,
      },
      {
        q: 'Is it water-resistant?',
        a: `The ${brand.name} pendant is designed for everyday wear but is not water-resistant. Avoid submerging it or exposing it to heavy rain.`,
      },
      {
        q: 'What happens if I lose or break the device?',
        a: `All your conversations and memories remain accessible through the ${brand.name} app on your phone, desktop, or browser. Your data is never stored only on the device.`,
      },
      {
        q: 'Can it hear only me or everyone?',
        a: `${brand.name} captures what you hear and say, so it can pick up other voices nearby. Always get permission to record others and follow local recording laws.`,
      },
    ],
  },
  {
    title: 'Pricing & Subscription',
    items: [
      {
        q: 'How much does it cost?',
        a: `The ${brand.name} device is a one-time purchase. It includes an unlimited free plan with on-device transcription, plus free cloud transcription minutes every month. Unlimited cloud transcription is available with a subscription.`,
      },
      {
        q: 'Do I need a subscription?',
        a: `No. ${brand.name} includes a generous free plan. On-device transcription is unlimited and free. Cloud transcription comes with free monthly minutes. You can upgrade anytime for unlimited cloud processing.`,
      },
      {
        q: 'Can I try it before buying hardware?',
        a: `Yes. Download the ${brand.name} app and use it with your phone or browser — no hardware required. The app records and transcribes conversations using your device microphone.`,
      },
    ],
  },
  {
    title: 'Privacy & Security',
    items: [
      {
        q: 'How safe is my data?',
        a: `Your data is encrypted in transit (TLS) and at rest (AES-256). ${brand.name} can run locally so your data never leaves your device. We never sell your data or use it for AI training. You can export or delete everything at any time.`,
      },
      {
        q: 'Where are conversations stored?',
        a: 'Conversations can be stored locally on your phone or on the cloud. All cloud data is encrypted. Everything can be deleted in one click from the app.',
      },
      {
        q: 'Is it compliant with enterprise security requirements?',
        a: `${brand.name} meets enterprise-grade standards including SOC 2 and HIPAA compliance. Data is encrypted end-to-end with immutable audit logs and strict access controls.`,
      },
      {
        q: 'Can I delete all my data?',
        a: `Yes. You can delete individual conversations, memories, or wipe all data entirely from the app settings. We also provide a full data export feature so you can take your data with you.`,
      },
    ],
  },
  {
    title: 'Apps & Integrations',
    items: [
      {
        q: `What apps work with ${brand.name}?`,
        a: `The ${brand.name} App Store has thousands of apps for productivity, integrations, health, education, and more. Popular integrations include Slack, Notion, Linear, Zapier, and GitHub.`,
      },
      {
        q: 'Can I build my own app?',
        a: 'Yes. You can create prompt-based apps (no server required) or integration apps with webhooks. Check our developer docs for guides on building and publishing apps.',
      },
      {
        q: 'Does it work with Zoom, Meet, and other video call tools?',
        a: `Yes. ${brand.name} works with any meeting tool — Zoom, Google Meet, Microsoft Teams, Slack calls, and more. No bot joins your meeting. It captures audio directly.`,
      },
    ],
  },
  {
    title: 'Getting Started',
    items: [
      {
        q: 'How technical do I need to be?',
        a: `No tech skills needed. ${brand.name} is designed to be simple. Charge it, turn it on, connect it to your phone in the app, hit record, and you'll get automatic transcripts, summaries, and action items.`,
      },
      {
        q: 'Does it need a phone?',
        a: `Yes for initial setup and sync. ${brand.name} works with all iPhone and Android models. There's also a Mac desktop app and a web app for any browser.`,
      },
      {
        q: 'How accurate is the transcription?',
        a: `${brand.name} uses state-of-the-art speech recognition with speaker identification. Accuracy improves over time with speech profiles. Custom vocabulary and jargon support ensures technical terms are captured correctly.`,
      },
    ],
  },
];

export function FaqContent() {
  const heroRef = useRef<HTMLDivElement>(null);
  const groupsRef = useRef<HTMLDivElement>(null);
  const [activeGroup, setActiveGroup] = useState<string | null>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const heroEls = heroRef.current?.querySelectorAll('.hero-anim');
      if (heroEls) {
        gsap.fromTo(heroEls, { opacity: 0, y: 30 }, {
          opacity: 1, y: 0, duration: 0.8, stagger: 0.1, ease: 'power3.out',
        });
      }

      const groups = groupsRef.current?.querySelectorAll('.faq-group');
      if (groups) {
        gsap.fromTo(groups, { opacity: 0, y: 30 }, {
          opacity: 1, y: 0, duration: 0.6, stagger: 0.1, ease: 'power2.out',
          scrollTrigger: { trigger: groupsRef.current, start: 'top 85%' },
        });
      }
    });
    return () => ctx.revert();
  }, []);

  const filteredGroups = activeGroup
    ? faqGroups.filter((g) => g.title === activeGroup)
    : faqGroups;

  return (
    <>
      <Navbar />
      <main className="pt-16 min-h-screen">
        {/* Hero */}
        <section className="pt-20 pb-12 px-6">
          <div ref={heroRef} className="mx-auto max-w-3xl text-center">
            <h1 className="hero-anim font-display font-bold text-4xl md:text-5xl lg:text-6xl mb-4">
              Frequently Asked Questions
            </h1>
            <p className="hero-anim text-text-tertiary text-lg max-w-xl mx-auto mb-10">
              Everything you need to know about {brand.name}. Can&apos;t find what you&apos;re looking for? Contact us.
            </p>

            {/* Group filter pills */}
            <div className="hero-anim flex gap-2 overflow-x-auto no-scrollbar pb-2 justify-center">
              <button
                onClick={() => setActiveGroup(null)}
                className={`flex-shrink-0 px-4 py-2 rounded-full text-xs font-medium whitespace-nowrap transition-all ${
                  !activeGroup ? 'bg-brand text-white' : 'bg-white/[0.06] text-text-tertiary hover:text-white hover:bg-white/10'
                }`}
              >
                All
              </button>
              {faqGroups.map((group) => (
                <button
                  key={group.title}
                  onClick={() => setActiveGroup(activeGroup === group.title ? null : group.title)}
                  className={`flex-shrink-0 px-4 py-2 rounded-full text-xs font-medium whitespace-nowrap transition-all ${
                    activeGroup === group.title
                      ? 'bg-brand text-white'
                      : 'bg-white/[0.06] text-text-tertiary hover:text-white hover:bg-white/10'
                  }`}
                >
                  {group.title}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ Groups */}
        <section className="pb-24 px-6">
          <div ref={groupsRef} className="mx-auto max-w-3xl">
            {filteredGroups.map((group) => (
              <div key={group.title} className="faq-group mb-12">
                <h2 className="font-display font-bold text-xl mb-5 text-text-secondary">{group.title}</h2>
                <div className="space-y-2">
                  {group.items.map((item) => (
                    <FaqAccordion key={item.q} question={item.q} answer={item.a} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Contact CTA */}
        <section className="pb-24 px-6">
          <div className="mx-auto max-w-3xl">
            <div className="rounded-2xl border border-white/10 bg-bg-secondary p-8 md:p-10 flex flex-col md:flex-row items-center justify-between gap-6">
              <div>
                <h3 className="font-display font-bold text-xl mb-2">Still have questions?</h3>
                <p className="text-text-tertiary text-sm">
                  Our team is here to help. Reach out and we&apos;ll get back to you shortly.
                </p>
              </div>
              <a
                href={`mailto:${brand.email}`}
                className="flex items-center gap-2 bg-brand hover:bg-brand-dark text-white text-sm font-medium px-6 py-3 rounded-full transition-colors flex-shrink-0"
              >
                <Mail size={16} /> Contact us
              </a>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}

function FaqAccordion({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-white/[0.06] rounded-xl overflow-hidden hover:border-white/10 transition-colors">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-white/[0.02] transition-colors"
      >
        <span className="font-display font-medium text-sm pr-4">{question}</span>
        <ChevronDown
          size={16}
          className={`text-text-tertiary transition-transform flex-shrink-0 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="px-5 pb-4 text-text-tertiary text-sm leading-relaxed border-t border-white/5 pt-3">
          {answer}
        </div>
      )}
    </div>
  );
}
