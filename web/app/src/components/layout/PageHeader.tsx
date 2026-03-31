'use client';

import { ArrowLeft, LucideIcon } from 'lucide-react';
import { useRouter } from 'next/navigation';

interface PageHeaderProps {
  title: string;
  icon?: LucideIcon;
  showBackButton?: boolean;
  onBack?: () => void;
}

export function PageHeader({ title, icon: Icon, showBackButton, onBack }: PageHeaderProps) {
  const router = useRouter();

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      router.back();
    }
  };

  return (
    <div className="flex items-center gap-3 px-6 h-16 border-b border-border/50">
      {showBackButton && (
        <button
          onClick={handleBack}
          className="p-1.5 rounded-lg hover:bg-secondary transition-colors -ml-1"
        >
          <ArrowLeft className="w-4 h-4 text-muted-foreground" />
        </button>
      )}
      {Icon && <Icon className="w-4 h-4 text-muted-foreground" />}
      <h1 className="text-sm font-medium text-foreground">{title}</h1>
    </div>
  );
}
