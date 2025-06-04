
import { Button } from '@/components/ui/button';

export const Footer = () => (
  <footer className="max-w-4xl mx-auto px-4 py-4">
    <div className="flex flex-col sm:flex-row justify-between text-xs text-zinc-400">
      <span className="mb-2 sm:mb-0 sm:mr-8">Omi by Based Hardware © 2025</span>
      <div className="flex gap-2">
        <Button variant="link" className="p-0 h-auto text-xs text-zinc-400 hover:text-white">Terms & Conditions</Button>
        <Button variant="link" className="p-0 h-auto text-xs text-zinc-400 hover:text-white">Privacy Policy</Button>
      </div>
    </div>
  </footer>
);
