'use client';

import { ArrowLeft, LucideIcon } from 'lucide-react';
import { useRouter } from '@tschk/moonshine-next/navigation';

interface PageHeaderProps {
  title: string;
  icon?: LucideIcon;
  showBackButton?: boolean;
  onBack?: () => void;
}

export function PageHeader({
  title,
  icon: Icon,
  showBackButton,
  onBack,
}: PageHeaderProps) {
  const router = useRouter();

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      router.back();
    }
  };

  return (
    <div className="flex items-center gap-3 border-b border-bg-tertiary bg-bg-secondary px-6 py-4">
      {showBackButton && (
        <button
          onClick={handleBack}
          className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
        >
          <ArrowLeft className="h-5 w-5 text-text-secondary" />
        </button>
      )}
      {Icon && <Icon className="h-6 w-6 text-text-secondary" />}
      <h1 className="text-2xl font-bold text-text-primary">{title}</h1>
    </div>
  );
}
