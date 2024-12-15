import Link from 'next/link';
import { Button } from "@/components/ui/button";

export function Footer() {
  return (
    <div className="fixed bottom-4 w-full max-w-4xl mx-auto px-4">
      <div className="flex justify-between text-sm text-white/60">
        <span>Omi Chat © 2024</span>
        <div className="flex gap-4">
          <Button variant="link" className="p-0 h-auto text-white/60 hover:text-white">Terms & Conditions</Button>
          <Link href="https://www.omi.me/pages/privacy" target="_blank" rel="noopener noreferrer">
            <Button variant="link" className="p-0 h-auto text-white/60 hover:text-white">Privacy Policy</Button>
          </Link>
        </div>
      </div>
    </div>
  );
} 