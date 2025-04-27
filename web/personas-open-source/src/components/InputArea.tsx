/**
 * @fileoverview InputArea Component for OMI Personas
 * @description Renders the input field and button for creating new AI personas
 * @author HarshithSunku
 * @license MIT
 */
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import Image from 'next/image';

interface InputAreaProps {
  handle: string;
  handleInputChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleCreatePersona: (inputHandle?: string) => void;
  isCreating: boolean;
  handleIntegrationClick?: (provider: string) => void;
  isIntegrating?: boolean;
}

export const InputArea: React.FC<InputAreaProps> = ({ handle, handleInputChange, handleCreatePersona, isCreating, handleIntegrationClick, isIntegrating }) => (
  <>
    {/* Create Section - Heading Only */}
    <div className="text-center mx-auto">
      <h1 className="text-4xl md:text-5xl font-serif font-bold mb-6 md:mb-8">Make Your ChatGPT 5x more personal</h1>
    </div>

    {/* Separated Paragraph */}
    <p className="text-gray-400 text-sm md:text-base text-center mb-4">
      Choose your most used app and connect it to ChatGPT
    </p>
    
    <div className="w-full max-w-sm space-y-4 mb-6 md:mb-8">
      {/* Integration Logos/Buttons */}
      <div className="flex justify-center items-center space-x-6 pb-4">
        <button
          onClick={() => handleIntegrationClick?.('notion')}
          className="transition-opacity hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Connect Notion"
          disabled={isIntegrating}
        >
          <Image src="/logos/notion-logo.png" alt="Notion Logo" width={56} height={56} />
        </button>
        <button
          onClick={() => handleIntegrationClick?.('mail')}
          className="transition-opacity hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Connect Gmail"
          disabled={isIntegrating}
        >
          <Image src="/logos/gmail-logo.png" alt="Gmail Logo" width={64} height={64} />
        </button>
        <button
          onClick={() => handleIntegrationClick?.('google-calendar')}
          className="transition-opacity hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Connect Google Calendar"
          disabled={isIntegrating}
        >
          <Image src="/logos/calendar-logo.png" alt="Google Calendar Logo" width={56} height={56} />
        </button>
        <button
          onClick={() => handleIntegrationClick?.('linkedin')}
          className="transition-opacity hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Connect LinkedIn"
          disabled={isIntegrating}
        >
          <Image src="/logos/linkedin-logo.svg" alt="LinkedIn Logo" width={56} height={56} />
        </button>
        <button
          onClick={() => handleIntegrationClick?.('x')}
          className="transition-opacity hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Connect X (Twitter)"
          disabled={isIntegrating}
        >
          <Image src="/logos/x-logo.svg" alt="X Logo" width={50} height={50} />
        </button>
      </div>
    </div>
  </>
);
