'use client';

import { Button } from "@/components/ui/button";
import { X } from 'lucide-react';
import Link from 'next/link';
import Image from 'next/image';

interface DevicePopupProps {
  isVisible: boolean;
  onClose: () => void;
}

export function DevicePopup({
  isVisible,
  onClose
}: DevicePopupProps) {
  return (
    <div className={`fixed bottom-48 right-4 z-50 transition-all duration-500 ${
      isVisible ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-full pointer-events-none'
    }`}>
      <Link
        href="https://www.omi.me/products/omi-dev-kit-2?ref=personas&utm_source=personas.omi.me&utm_campaign=personas_chat"
        target="_blank"
        rel="noopener noreferrer"
        className="relative block w-[220px] h-[200px] rounded-2xl overflow-hidden shadow-2xl bg-black"
      >
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-black/20 to-black/80">
          <Image
            src="/omidevice.webp"
            alt="Omi Device"
            width={220}
            height={200}
            className="w-full h-full object-cover"
          />
        </div>
        <div className="absolute bottom-2 left-0 right-0 text-center">
          <p className="text-white text-[14px] font-bold tracking-wide">
            Take your ai clone with you.
          </p>
        </div>
        <Button
          onClick={(e) => {
            e.preventDefault();
            onClose();
          }}
          className="absolute top-4 right-4 text-white/80 hover:text-white transition-colors"
        >
          <X className="h-6 w-6" />
        </Button>
      </Link>
    </div>
  );
}
