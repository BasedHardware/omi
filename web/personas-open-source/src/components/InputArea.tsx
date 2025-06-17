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

export const InputArea: React.FC<InputAreaProps> = ({
  handle,
  handleInputChange,
  handleCreatePersona,
  isCreating,
  handleIntegrationClick,
  isIntegrating,
}) => (
  <>
    {/* Create Section - Heading Only */}
    <div className="mx-auto text-center">
      <h1 className="mb-6 font-serif text-4xl font-bold md:mb-8 md:text-5xl">
        Make Your ChatGPT 5x more personal
      </h1>
    </div>

    {/* Step 1 Instruction */}
    <p className="mb-4 text-center text-sm font-semibold text-gray-400 md:text-base">
      Step 1: Pick an app to connect
    </p>

    <div className="mb-6 w-full max-w-sm space-y-4 md:mb-8">
      {/* Integration Logos/Buttons */}
      <div className="flex items-center justify-center space-x-6 pb-4">
        {/* Notion */}
        <div className="flex flex-col items-center">
          <button
            onClick={() => handleIntegrationClick?.('notion')}
            className="rounded-lg border border-zinc-700 bg-zinc-900 p-3 shadow-md transition hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Connect Notion"
            disabled={isIntegrating}
          >
            <Image
              src="/logos/notion-logo.png"
              alt="Notion Logo"
              width={56}
              height={56}
            />
          </button>
          <span className="mt-2 text-xs">Notion</span>
        </div>

        {/* Gmail */}
        <div className="flex flex-col items-center">
          <button
            onClick={() => handleIntegrationClick?.('mail')}
            className="rounded-lg border border-zinc-700 bg-zinc-900 p-3 shadow-md transition hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Connect Gmail"
            disabled={isIntegrating}
          >
            <Image src="/logos/gmail-logo.png" alt="Gmail Logo" width={56} height={56} />
          </button>
          <span className="mt-2 text-xs">Gmail</span>
        </div>

        {/* Calendar */}
        <div className="flex flex-col items-center">
          <button
            onClick={() => handleIntegrationClick?.('google-calendar')}
            className="rounded-lg border border-zinc-700 bg-zinc-900 p-3 shadow-md transition hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Connect Google Calendar"
            disabled={isIntegrating}
          >
            <Image
              src="/logos/calendar-logo.png"
              alt="Google Calendar Logo"
              width={56}
              height={56}
            />
          </button>
          <span className="mt-2 text-xs">Calendar</span>
        </div>

        {/* LinkedIn */}
        <div className="flex flex-col items-center">
          <button
            onClick={() => handleIntegrationClick?.('linkedin')}
            className="rounded-lg border border-zinc-700 bg-zinc-900 p-3 shadow-md transition hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Connect LinkedIn"
            disabled={isIntegrating}
          >
            <Image
              src="/logos/linkedin-logo.svg"
              alt="LinkedIn Logo"
              width={56}
              height={56}
            />
          </button>
          <span className="mt-2 text-xs">LinkedIn</span>
        </div>

        {/* X */}
        <div className="flex flex-col items-center">
          <button
            onClick={() => handleIntegrationClick?.('x')}
            className="rounded-lg border border-zinc-700 bg-zinc-900 p-3 shadow-md transition hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Connect X (Twitter)"
            disabled={isIntegrating}
          >
            <Image src="/logos/x-logo.svg" alt="X Logo" width={50} height={50} />
          </button>
          <span className="mt-2 text-xs">X</span>
        </div>
      </div>
    </div>
  </>
);
