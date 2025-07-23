/**
 * @fileoverview Footer Component for OMI Personas
 * @description Renders the application footer with copyright and legal links
 * @author HarshithSunku
 * @license MIT
 */
import { Button } from '@/components/ui/button';

/**
 * Footer Component
 *
 * @component
 * @description Renders a footer with copyright notice and legal links
 * @returns {JSX.Element} Rendered Footer component
 */
export const Footer = () => (
  <footer className="mx-auto max-w-4xl px-4 py-4">
    <div className="flex flex-col justify-between text-xs text-zinc-400 sm:flex-row">
      <span className="mb-2 sm:mb-0 sm:mr-8">Omi by Based Hardware © 2025</span>
      <div className="flex gap-2">
        <Button
          variant="link"
          className="h-auto p-0 text-xs text-zinc-400 hover:text-white"
        >
          Terms & Conditions
        </Button>
        <Button
          variant="link"
          className="h-auto p-0 text-xs text-zinc-400 hover:text-white"
        >
          Privacy Policy
        </Button>
      </div>
    </div>
  </footer>
);
