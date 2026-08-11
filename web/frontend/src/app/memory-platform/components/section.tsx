import type { ReactNode } from 'react';
import { cn } from '@/src/lib/utils';

interface SectionProps {
  id?: string;
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  className?: string;
  children?: ReactNode;
}

export function Section({
  id,
  eyebrow,
  title,
  description,
  className,
  children,
}: SectionProps) {
  return (
    <section id={id} className={cn('mt-20 border-t border-white/10 pt-10', className)}>
      {eyebrow ? (
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#b9f36b]">
          {eyebrow}
        </p>
      ) : null}
      <h2 className="mt-3 text-2xl font-semibold tracking-tight text-white md:text-3xl">
        {title}
      </h2>
      {description ? (
        <div className="mt-3 max-w-2xl text-[15px] leading-7 text-neutral-400">
          {description}
        </div>
      ) : null}
      {children ? <div className="mt-8">{children}</div> : null}
    </section>
  );
}

interface HairlineCardProps {
  eyebrow?: string;
  title: string;
  children: ReactNode;
  className?: string;
}

export function HairlineCard({ eyebrow, title, children, className }: HairlineCardProps) {
  return (
    <article
      className={cn(
        'rounded-xl border border-white/10 bg-white/[0.02] p-5 transition-colors hover:border-white/20',
        className,
      )}
    >
      {eyebrow ? (
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-neutral-500">
          {eyebrow}
        </span>
      ) : null}
      <h3 className="mt-3 text-base font-semibold tracking-tight text-white">{title}</h3>
      <div className="mt-2 text-sm leading-6 text-neutral-400">{children}</div>
    </article>
  );
}
