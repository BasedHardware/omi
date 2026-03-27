'use client';

import { useRef, useEffect } from 'react';
import Image from 'next/image';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import { brand } from '@/lib/config';

gsap.registerPlugin(ScrollTrigger);

export function Hero() {
  const t = useTranslations('hero');
  const sectionRef = useRef<HTMLElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const deviceRef = useRef<HTMLDivElement>(null);
  const deviceInnerRef = useRef<HTMLDivElement>(null);
  const glowRef = useRef<HTMLDivElement>(null);
  const bgRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const text = textRef.current!;
      const device = deviceRef.current!;
      const inner = deviceInnerRef.current!;
      const glow = glowRef.current!;

      const bg = bgRef.current!;

      gsap.set(text, { opacity: 0, y: 40 });
      gsap.set(device, { opacity: 0 });
      gsap.set(bg, { opacity: 0, scale: 1.1 });

      // BG image fades in with slight scale
      gsap.to(bg, { opacity: 0.9, scale: 1, duration: 2, ease: 'power2.out', delay: 0.2 });

      gsap.to(text, { opacity: 1, y: 0, duration: 1.2, ease: 'power3.out', delay: 0.1, onComplete: () => {
        gsap.set(text, { clearProps: 'opacity,y,filter' });
      }});
      gsap.to(device, { opacity: 1, duration: 1.2, ease: 'power2.out', delay: 0.4, onComplete: () => {
        gsap.set(device, { clearProps: 'opacity' });
      }});

      const scrollTl = gsap.timeline({
        scrollTrigger: {
          trigger: sectionRef.current,
          start: 'top top',
          end: '+=150%',
          pin: true,
          scrub: 0.8,
          anticipatePin: 1,
        },
      });

      // Text fades out
      scrollTl.fromTo(text,
        { opacity: 1, y: 0, filter: 'blur(0px)' },
        { opacity: 0, y: -60, filter: 'blur(8px)', duration: 1, ease: 'power2.in' },
      );

      // BG image: scale up, fade, and blur
      scrollTl.fromTo(bg,
        { scale: 1, opacity: 0.9, filter: 'blur(0px)' },
        { scale: 1.15, opacity: 0.15, filter: 'blur(12px)', duration: 2.4, ease: 'power1.inOut' },
      '<');

      // Device rises to center
      scrollTl.fromTo(device,
        { y: 0 },
        { y: '-80%', duration: 2.4, ease: 'power2.inOut' },
      '<');

      // Device scales + rotates through angles
      scrollTl.fromTo(inner,
        { scale: 1, rotateY: 0, rotateX: 0 },
        { scale: 2, rotateY: 25, rotateX: -10, duration: 0.8, ease: 'power1.inOut' },
      '<');

      scrollTl.fromTo(inner,
        { scale: 2, rotateY: 25, rotateX: -10 },
        { scale: 2.8, rotateY: -20, rotateX: 15, duration: 0.8, ease: 'power1.inOut' },
      );

      scrollTl.fromTo(inner,
        { scale: 2.8, rotateY: -20, rotateX: 15 },
        { scale: 3.5, rotateY: 0, rotateX: 0, duration: 0.8, ease: 'power2.out' },
      );

      // Glow intensifies
      scrollTl.fromTo(glow,
        { scale: 1, opacity: 0.3 },
        { scale: 2.5, opacity: 0.8, duration: 2.4 },
      '<-2.4');

      // Hold
      scrollTl.to({}, { duration: 0.5 });
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="relative h-screen flex flex-col items-center justify-center overflow-hidden px-6">
      {/* Background image — extends behind navbar */}
      <div ref={bgRef} className="absolute -top-16 left-0 right-0 bottom-0 z-0" style={{ opacity: 0 }}>
        <Image
          src="/hero-bg.png"
          alt=""
          fill
          className="object-cover object-center"
          priority
          sizes="100vw"
        />
        {/* Clean overlay — dark enough to read, light enough to see the image */}
        <div className="absolute inset-0 bg-black/40" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-bg-primary" />
      </div>

      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-brand/[0.03] rounded-full blur-[150px]" />

      <div ref={textRef} className="relative z-10 text-center max-w-5xl mx-auto mb-16">
        <h1 className="font-display font-bold text-[clamp(2rem,5vw,4.5rem)] tracking-tight leading-[1.1] mb-8 text-white drop-shadow-[0_2px_30px_rgba(0,0,0,0.8)]">
          {t('heading')}
        </h1>
        <p className="text-white/90 text-lg md:text-xl max-w-xl mx-auto leading-relaxed mb-10 drop-shadow-[0_1px_15px_rgba(0,0,0,0.7)]">
          {t('description')}
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link href={brand.links.download} className="flex items-center gap-3 bg-white text-black font-medium text-sm px-7 py-3.5 rounded-full hover:bg-white/90 transition-all shadow-lg shadow-black/20">
            {t('getStarted')}
          </Link>
          <Link href={brand.links.tryBrowser} className="text-white hover:text-white text-sm font-medium border border-white/40 bg-white/15 backdrop-blur-sm px-7 py-3.5 rounded-full hover:bg-white/25 transition-all shadow-lg shadow-black/20">
            {t('tryInBrowser')}
          </Link>
        </div>
      </div>

      <div ref={deviceRef} className="relative z-10" style={{ perspective: '800px' }}>
        <div ref={deviceInnerRef} className="relative w-36 h-36 md:w-44 md:h-44" style={{ transformStyle: 'preserve-3d' }}>
          <div ref={glowRef} className="absolute inset-[-50%] rounded-full bg-brand/[0.08] blur-[80px] pointer-events-none" />
          <div className="absolute -top-14 left-1/2 -translate-x-1/2 w-px h-14 bg-gradient-to-t from-white/20 to-transparent" />
          <div className="relative w-full h-full rounded-full bg-gradient-to-b from-[#2a2a2a] to-[#1a1a1a] border border-white/10 flex items-center justify-center shadow-[0_0_60px_rgba(0,0,0,0.5)]">
            <div className="w-[75%] h-[75%] rounded-full bg-gradient-to-b from-[#333] to-[#222] border border-white/[0.08] flex items-center justify-center">
              <div className="w-[55%] h-[55%] rounded-full bg-gradient-to-br from-brand/40 to-brand/15 border border-brand/25 shadow-[0_0_40px_rgba(59,130,246,0.2)]" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
