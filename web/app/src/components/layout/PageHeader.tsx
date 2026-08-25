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
    <div className="flex items-center gap-3 px-6 py-4 border-b border-bg-tertiary bg-bg-secondary">
      {showBackButton && (
        <button
          onClick={handleBack}
          className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
        >
          <ArrowLeft className="w-5 h-5 text-text-secondary" />
        </button>
      )}
      {Icon && <Icon className="w-6 h-6 text-text-secondary" />}
      <h1 className="text-2xl font-bold text-text-primary">{title}</h1>
    </div>
  );
}
