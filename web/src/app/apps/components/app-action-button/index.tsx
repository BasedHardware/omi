/* eslint-disable prettier/prettier */
import { ArrowRight } from 'lucide-react';
import { Button } from '@/src/components/ui/button';
import Link from 'next/link';

interface AppActionButtonProps {
  link: string;
  className?: string;
}

export function AppActionButton({ link, className = '' }: AppActionButtonProps) {
  return (
    <Button
      className={`group relative inline-flex items-center justify-center overflow-hidden rounded-xl bg-[#6C8EEF] px-6 py-3 text-base font-medium text-white transition-all hover:bg-[#5A7DE8] ${className}`}
      asChild
    >
      <Link href={link}>
        <span className="relative z-10 flex items-center justify-center">
          Try it now
          <ArrowRight className="ml-2 h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
        </span>
        <div className="absolute inset-0 bg-gradient-to-r from-[#5A7DE8] to-[#4967D3] opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
      </Link>
    </Button>
  );
} 