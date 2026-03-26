import { type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface InfoCardProps {
  title: string;
  description: string;
  icon: LucideIcon;
  href?: string;
  className?: string;
}

export function InfoCard({ title, description, icon: Icon, href, className }: InfoCardProps) {
  const Wrapper = href ? 'a' : 'div';
  return (
    <Wrapper
      {...(href ? { href } : {})}
      className={cn(
        'block rounded-2xl border border-white/10 bg-bg-secondary p-6 transition-colors',
        href && 'hover:border-brand/30 hover:bg-bg-tertiary cursor-pointer',
        className,
      )}
    >
      <div className="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center mb-4">
        <Icon size={20} className="text-brand" />
      </div>
      <h3 className="font-display font-semibold text-base mb-2">{title}</h3>
      <p className="text-text-tertiary text-sm leading-relaxed">{description}</p>
    </Wrapper>
  );
}

interface InfoCardGroupProps {
  cols?: 2 | 3;
  children: React.ReactNode;
}

export function InfoCardGroup({ cols = 3, children }: InfoCardGroupProps) {
  return (
    <div className={cn('grid gap-4', cols === 2 ? 'md:grid-cols-2' : 'md:grid-cols-3')}>
      {children}
    </div>
  );
}
