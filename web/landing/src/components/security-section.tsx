'use client';

import { useRef, useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { Lock, Shield, Server, Eye, KeyRound } from 'lucide-react';
import { Link } from '@/i18n/navigation';
import { brand } from '@/lib/config';

gsap.registerPlugin(ScrollTrigger);

const items = [
  { icon: Lock, title: 'AES-256 encryption', body: 'Encrypted before it leaves your device. At rest, in transit, everywhere.', accent: false },
  { icon: Shield, title: 'TLS 1.3 in transit', body: 'Every connection secured. Nothing sent in plain text.', accent: false },
  { icon: Server, title: 'Runs on-device', body: 'Process everything locally. Your data never has to touch the cloud.', accent: false },
  { icon: Eye, title: 'Zero access', body: 'We cannot read your data. Not our engineers, not anyone.', accent: true },
  { icon: KeyRound, title: 'You own it all', body: 'Export, delete, bring your own keys. No hidden backups.', accent: false },
];

export function SecuritySection() {
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const section = sectionRef.current;
      if (!section) return;

      gsap.fromTo(section.querySelectorAll('.sec-anim'),
        { opacity: 0, y: 25 },
        { opacity: 1, y: 0, duration: 0.6, stagger: 0.08, ease: 'power3.out',
          scrollTrigger: { trigger: section, start: 'top 80%' },
        },
      );
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="py-24 md:py-32 px-6">
      <div className="mx-auto max-w-4xl">
        {/* Header */}
        <div className="sec-anim inline-flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-4 py-1.5 mb-6">
          <Shield size={14} className="text-emerald-400" />
          <span className="text-xs text-emerald-400 font-medium tracking-wide">Security first</span>
        </div>

        <h2 className="sec-anim font-display font-bold text-3xl md:text-5xl mb-4 leading-tight">
          Your conversations are <span className="text-emerald-400">yours alone.</span>
        </h2>

        <p className="sec-anim text-text-tertiary text-lg mb-16 max-w-xl">
          Every byte encrypted. Zero access by design. We built {brand.name} so even we cannot read your data.
        </p>

        {/* Items — clean vertical list */}
        <div className="space-y-10 mb-16">
          {items.map((item) => (
            <div key={item.title} className="sec-anim flex items-start gap-5">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${
                item.accent ? 'bg-red-500/10 border border-red-500/20' : 'bg-emerald-500/10 border border-emerald-500/20'
              }`}>
                <item.icon size={20} className={item.accent ? 'text-red-400' : 'text-emerald-400'} />
              </div>
              <div>
                <h3 className={`font-display font-semibold text-lg mb-1 ${item.accent ? 'text-red-400' : 'text-white'}`}>
                  {item.title}
                </h3>
                <p className="text-text-tertiary text-sm leading-relaxed">{item.body}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Compliance row */}
        <div className="sec-anim flex flex-wrap gap-4 mb-10">
          {['SOC 2', 'HIPAA', 'AES-256', 'TLS 1.3', 'GDPR'].map((label) => (
            <div key={label} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-emerald-500/15 bg-emerald-500/[0.04]">
              <Shield size={11} className="text-emerald-400" />
              <span className="text-xs text-emerald-400 font-medium">{label}</span>
            </div>
          ))}
        </div>

        <div className="sec-anim">
          <Link href="/privacy" className="text-emerald-400 text-sm font-medium hover:underline">
            Read our full privacy policy →
          </Link>
        </div>
      </div>
    </section>
  );
}
