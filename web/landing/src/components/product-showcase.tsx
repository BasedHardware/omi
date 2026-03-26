'use client';

import { useRef, useEffect } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { Rewind } from 'lucide-react';
import { brand } from '@/lib/config';

gsap.registerPlugin(ScrollTrigger);

export function ProductShowcase() {
  const sectionRef = useRef<HTMLElement>(null);
  const mockupRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef<HTMLDivElement>(null);
  const mockupInnerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      // Scroll reveal
      gsap.fromTo(mockupRef.current,
        { opacity: 0, y: 60 },
        { opacity: 1, y: 0, duration: 1.2, ease: 'power3.out',
          scrollTrigger: { trigger: sectionRef.current, start: 'top 70%', end: 'top 30%', scrub: 1 },
        },
      );
      gsap.fromTo(textRef.current,
        { opacity: 0, y: 40 },
        { opacity: 1, y: 0, duration: 1, ease: 'power3.out',
          scrollTrigger: { trigger: sectionRef.current, start: 'top 80%', end: 'top 40%', scrub: 1 },
        },
      );

      // Interactive cursor animation
      const cursor = cursorRef.current!;
      const inner = mockupInnerRef.current!;

      const contentCards = inner.querySelectorAll('.content-card');
      const actionLines = inner.querySelectorAll('.action-line');
      const summaryLines = inner.querySelectorAll('.summary-line');
      const transcriptLines = inner.querySelectorAll('.transcript-line');
      const rewindLines = inner.querySelectorAll('.rewind-line');
      const clickRipple = inner.querySelector('.click-ripple')!;
      const selectBar = inner.querySelector('.select-bar')!;

      gsap.set(cursor, { opacity: 0, x: 20, y: 20 });
      gsap.set(contentCards, { opacity: 0, y: 15 });
      gsap.set(actionLines, { opacity: 0, scaleX: 0, transformOrigin: 'left' });
      gsap.set(summaryLines, { opacity: 0, scaleX: 0, transformOrigin: 'left' });
      gsap.set(transcriptLines, { opacity: 0, scaleX: 0, transformOrigin: 'left' });
      gsap.set(rewindLines, { opacity: 0, scaleX: 0, transformOrigin: 'left' });
      gsap.set(clickRipple, { opacity: 0, scale: 0 });
      gsap.set(selectBar, { opacity: 0 });

      const demoTl = gsap.timeline({
        repeat: -1,
        repeatDelay: 1.5,
        scrollTrigger: {
          trigger: sectionRef.current,
          start: 'top 60%',
          toggleActions: 'play pause resume pause',
        },
      });
      // Cursor appears
      demoTl.to(cursor, { opacity: 1, duration: 0.3 });

      // Click Conversations
      demoTl.to(cursor, { x: 90, y: 75, duration: 0.6, ease: 'power2.inOut' });
      demoTl.to(clickRipple, { opacity: 0.4, scale: 1, duration: 0.15, x: 90, y: 75 });
      demoTl.to(clickRipple, { opacity: 0, scale: 1.5, duration: 0.3 });
      demoTl.to(selectBar, { opacity: 1, duration: 0.2 }, '<');

      // Content cards stagger in
      demoTl.to(contentCards, { opacity: 1, y: 0, duration: 0.4, stagger: 0.12, ease: 'power2.out' }, '-=0.1');

      // Click Action Items
      demoTl.to(cursor, { x: 400, y: 170, duration: 0.8, ease: 'power2.inOut' });
      demoTl.to(cursor, { scale: 0.9, duration: 0.08, yoyo: true, repeat: 1 });
      demoTl.to(actionLines, { opacity: 1, scaleX: 1, duration: 0.3, stagger: 0.1, ease: 'power2.out' });

      demoTl.to({}, { duration: 0.6 });

      // Click Summary
      demoTl.to(cursor, { x: 700, y: 170, duration: 0.7, ease: 'power2.inOut' });
      demoTl.to(cursor, { scale: 0.9, duration: 0.08, yoyo: true, repeat: 1 });
      demoTl.to(summaryLines, { opacity: 1, scaleX: 1, duration: 0.25, stagger: 0.08, ease: 'power2.out' });

      demoTl.to({}, { duration: 0.5 });

      // Click Transcript
      demoTl.to(cursor, { x: 400, y: 340, duration: 0.5, ease: 'power2.inOut' });
      demoTl.to(cursor, { scale: 0.9, duration: 0.08, yoyo: true, repeat: 1 });
      demoTl.to(transcriptLines, { opacity: 1, scaleX: 1, duration: 0.2, stagger: 0.06, ease: 'power2.out' });

      demoTl.to({}, { duration: 0.5 });

      // Click Rewind
      demoTl.to(cursor, { x: 700, y: 340, duration: 0.6, ease: 'power2.inOut' });
      demoTl.to(cursor, { scale: 0.9, duration: 0.08, yoyo: true, repeat: 1 });
      demoTl.to(rewindLines, { opacity: 1, scaleX: 1, duration: 0.25, stagger: 0.08, ease: 'power2.out' });

      // Pause at end
      demoTl.to({}, { duration: 1.5 });

      // Reset
      demoTl.to(cursor, { opacity: 0, duration: 0.3 });
      demoTl.set([contentCards, actionLines, summaryLines, transcriptLines, rewindLines, selectBar], { opacity: 0, y: 15, scaleX: 0 });
      demoTl.set(contentCards, { y: 15 });
      demoTl.set(cursor, { x: 20, y: 20, scale: 1 });

    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section ref={sectionRef} className="py-24 md:py-32 overflow-hidden">
      <div className="mx-auto max-w-7xl px-6">
        {/* Text */}
        <div ref={textRef} className="text-center mb-20 max-w-2xl mx-auto">
          <h2 className="font-display font-bold text-3xl md:text-4xl lg:text-5xl mb-5 leading-tight">
            Your meetings, <span className="text-brand">summarized.</span>
          </h2>
          <p className="text-text-tertiary text-lg leading-relaxed">
            {brand.name} automatically captures your conversations and transforms them into structured summaries, action items, and searchable transcripts.
          </p>
        </div>

        {/* Mockup */}
        <div ref={mockupRef}>
          <div
            ref={mockupInnerRef}
            className="relative aspect-[16/9] rounded-2xl overflow-hidden bg-bg-secondary border border-white/10 shadow-2xl shadow-black/50"
          >
            {/* Custom cursor */}
            <div ref={cursorRef} className="absolute z-30 pointer-events-none" style={{ width: 20, height: 20 }}>
              <svg width="20" height="20" viewBox="0 0 18 18" fill="none">
                <path d="M1 1L7 17L9.5 10L17 7.5L1 1Z" fill="white" stroke="black" strokeWidth="1" />
              </svg>
            </div>

            {/* Click ripple */}
            <div className="click-ripple absolute z-20 w-8 h-8 rounded-full border border-brand/50 pointer-events-none" />

            <div className="absolute inset-0 flex">
              {/* Sidebar */}
              <div className="w-56 bg-bg-primary border-r border-white/5 p-5">
                <div className="w-20 h-5 bg-white/10 rounded mb-8" />
                <div className="space-y-1 relative">
                  <div className="select-bar absolute top-0 left-0 right-0 h-10 rounded-lg bg-brand/10" />
                  {['Conversations', 'Chat', 'Memories', 'Actions', 'Apps'].map((item, i) => (
                    <div
                      key={item}
                      className={`sb-item relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm ${i === 0 ? 'text-brand' : 'text-text-tertiary'}`}
                    >
                      <div className={`w-4 h-4 rounded ${i === 0 ? 'bg-brand/30' : 'bg-white/10'}`} />
                      {item}
                    </div>
                  ))}
                </div>
              </div>

              {/* Content */}
              <div className="flex-1 p-6 md:p-8 overflow-hidden">
                {/* Header */}
                <div className="content-card">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <div className="text-base font-medium text-white">Team Discusses Inbound Sales and Demo Process</div>
                      <div className="text-sm text-text-tertiary mt-1">Today at 2:30 PM · 45 min · 3 participants</div>
                    </div>
                    <div className="flex gap-2">
                      <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/10" />
                      <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/10" />
                      <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/10" />
                    </div>
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  {/* Action Items */}
                  <div className="content-card bg-bg-tertiary rounded-xl p-4">
                    <div className="text-sm font-medium text-brand mb-3">Action Items</div>
                    <div className="space-y-2">
                      <div className="action-line h-2.5 rounded bg-brand/20" style={{ width: '90%' }} />
                      <div className="action-line h-2.5 rounded bg-brand/15" style={{ width: '75%' }} />
                      <div className="action-line h-2.5 rounded bg-brand/10" style={{ width: '60%' }} />
                    </div>
                  </div>

                  {/* Summary */}
                  <div className="content-card bg-bg-tertiary rounded-xl p-4">
                    <div className="text-sm font-medium text-white mb-3">Summary</div>
                    <div className="space-y-2">
                      <div className="summary-line h-2.5 rounded bg-white/[0.08]" style={{ width: '95%' }} />
                      <div className="summary-line h-2.5 rounded bg-white/[0.06]" style={{ width: '85%' }} />
                      <div className="summary-line h-2.5 rounded bg-white/[0.06]" style={{ width: '70%' }} />
                      <div className="summary-line h-2.5 rounded bg-white/[0.05]" style={{ width: '50%' }} />
                    </div>
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-4 mt-4">
                  {/* Transcript */}
                  <div className="content-card bg-bg-tertiary rounded-xl p-4">
                    <div className="text-sm font-medium text-white mb-3">Transcript</div>
                    <div className="space-y-2">
                      <div className="transcript-line h-2.5 rounded bg-white/[0.06]" style={{ width: '100%' }} />
                      <div className="transcript-line h-2.5 rounded bg-white/[0.06]" style={{ width: '92%' }} />
                      <div className="transcript-line h-2.5 rounded bg-white/[0.05]" style={{ width: '88%' }} />
                      <div className="transcript-line h-2.5 rounded bg-white/[0.05]" style={{ width: '95%' }} />
                      <div className="transcript-line h-2.5 rounded bg-white/[0.04]" style={{ width: '60%' }} />
                    </div>
                  </div>

                  {/* Rewind */}
                  <div className="content-card bg-bg-tertiary rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <Rewind size={14} className="text-brand" />
                      <div className="text-sm font-medium text-white">Rewind</div>
                    </div>
                    <div className="text-xs text-text-tertiary mb-3">Search across all your past conversations</div>
                    <div className="space-y-2">
                      <div className="rewind-line h-2.5 rounded bg-brand/[0.12]" style={{ width: '80%' }} />
                      <div className="rewind-line h-2.5 rounded bg-brand/[0.08]" style={{ width: '65%' }} />
                      <div className="rewind-line h-2.5 rounded bg-brand/[0.06]" style={{ width: '90%' }} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
