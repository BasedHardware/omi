import { cn } from '@/lib/utils';

export function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-2xl p-5',
        // Layered background for depth instead of harsh border
        'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
        // Soft shadow stack
        'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]',
        className,
      )}
    >
      {children}
    </div>
  );
}
