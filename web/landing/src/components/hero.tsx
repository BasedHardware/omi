'use client';

import { useRef, useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Link from 'next/link';
import { brand } from '@/lib/config';

gsap.registerPlugin(ScrollTrigger);

export function Hero() {
  const sectionRef = useRef<HTMLElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const deviceRef = useRef<HTMLDivElement>(null);
  const deviceInnerRef = useRef<HTMLDivElement>(null);
  const glowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const text = textRef.current!;
      const device = deviceRef.current!;
      const inner = deviceInnerRef.current!;
      const glow = glowRef.current!;

      // Entrance: simple CSS transition approach — set initial hidden, then reveal
      gsap.set(text, { opacity: 0, y: 40 });
      gsap.set(device, { opacity: 0 });

      gsap.to(text, { opacity: 1, y: 0, duration: 1.2, ease: 'power3.out', delay: 0.1, onComplete: () => {
        // Clear inline styles so scroll timeline is the only controller
        gsap.set(text, { clearProps: 'opacity,y,filter' });
      }});
      gsap.to(device, { opacity: 1, duration: 1.2, ease: 'power2.out', delay: 0.4, onComplete: () => {
        gsap.set(device, { clearProps: 'opacity' });
      }});

      // Scroll-driven: text fades, device expands
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

      // Text fades up and blurs out
      scrollTl.fromTo(text,
        { opacity: 1, y: 0, filter: 'blur(0px)' },
        { opacity: 0, y: -60, filter: 'blur(8px)', duration: 1, ease: 'power2.in' },
      );

      // Device scales up + rotates through angles
      scrollTl.fromTo(inner,
        { scale: 1, rotateY: 0, rotateX: 0 },
        { scale: 2, rotateY: 25, rotateX: -10, duration: 0.8, ease: 'power1.inOut' },
      '<');

      scrollTl.to(inner, {
        scale: 2.8,
        rotateY: -20,
        rotateX: 15,
        duration: 0.8,
        ease: 'power1.inOut',
      });

      scrollTl.to(inner, {
        scale: 3.5,
        rotateY: 0,
        rotateX: 0,
        duration: 0.8,
        ease: 'power2.out',
      });

      // Glow intensifies
      scrollTl.fromTo(glow,
        { scale: 1, opacity: 0.3 },
        { scale: 2.5, opacity: 0.8, duration: 2.4 },
      '<-2.4');

      // Hold at full scale before unpin
      scrollTl.to({}, { duration: 0.5 });
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="relative h-screen flex flex-col items-center justify-center overflow-hidden px-6">
      {/* Background glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-brand/[0.03] rounded-full blur-[150px]" />

      {/* Text content */}
      <div ref={textRef} className="relative z-10 text-center max-w-5xl mx-auto mb-16">
        <h1 className="font-display font-bold text-[clamp(2rem,5vw,4.5rem)] tracking-tight leading-[1.1] mb-8">
          Personal intelligence that turns thought to action.
        </h1>
        <p className="text-text-tertiary text-lg md:text-xl max-w-xl mx-auto leading-relaxed mb-10">
          {brand.name} captures your meetings and conversations, creates summaries, tasks, and memories — across every device you own.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link href={brand.links.download} className="flex items-center gap-3 bg-white text-black font-medium text-sm px-7 py-3.5 rounded-full hover:bg-white/90 transition-all hover:shadow-lg hover:shadow-white/10">
            Get started
          </Link>
          <Link href={brand.links.tryBrowser} className="text-text-secondary hover:text-white text-sm font-medium border border-white/10 px-7 py-3.5 rounded-full hover:border-white/20 transition-all">
            Try in browser
          </Link>
        </div>
      </div>

      {/* Device — expands on scroll */}
      <div ref={deviceRef} className="relative z-10" style={{ perspective: '800px' }}>
        <div ref={deviceInnerRef} className="relative w-36 h-36 md:w-44 md:h-44" style={{ transformStyle: 'preserve-3d' }}>
          {/* Glow behind device */}
          <div
            ref={glowRef}
            className="absolute inset-[-50%] rounded-full bg-brand/[0.08] blur-[80px] pointer-events-none"
          />
          {/* Necklace line */}
          <div className="absolute -top-14 left-1/2 -translate-x-1/2 w-px h-14 bg-gradient-to-t from-white/20 to-transparent" />
          {/* Outer ring */}
          <div className="relative w-full h-full rounded-full bg-gradient-to-b from-[#2a2a2a] to-[#1a1a1a] border border-white/10 flex items-center justify-center shadow-[0_0_60px_rgba(0,0,0,0.5)]">
            {/* Mid ring */}
            <div className="w-[75%] h-[75%] rounded-full bg-gradient-to-b from-[#333] to-[#222] border border-white/[0.08] flex items-center justify-center">
              {/* Core — brand glow */}
              <div className="w-[55%] h-[55%] rounded-full bg-gradient-to-br from-brand/40 to-brand/15 border border-brand/25 shadow-[0_0_40px_rgba(59,130,246,0.2)]" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
