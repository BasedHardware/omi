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

    {/* Step 1 Instruction */}
    <p className="text-gray-400 text-sm md:text-base text-center mb-4 font-semibold">
      Step 1: Pick an app to connect
    </p>
    
    <div className="w-full max-w-sm space-y-4 mb-6 md:mb-8">
      {/* Integration Logos/Buttons */}
      <div className="flex justify-center items-center space-x-6 pb-4">
        {/* Notion */}
        <div className="flex flex-col items-center">
          <button
            onClick={() => handleIntegrationClick?.('notion')}
            className="bg-zinc-900 border border-zinc-700 shadow-md p-3 rounded-lg transition hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Connect Notion"
            disabled={isIntegrating}
          >
            <Image src="/logos/notion-logo.png" alt="Notion Logo" width={56} height={56} />
          </button>
          <span className="text-xs mt-2">Notion</span>
        </div>

        {/* Gmail */}
        <div className="flex flex-col items-center">
          <button
            onClick={() => handleIntegrationClick?.('mail')}
            className="bg-zinc-900 border border-zinc-700 shadow-md p-3 rounded-lg transition hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Connect Gmail"
            disabled={isIntegrating}
          >
            <Image src="/logos/gmail-logo.png" alt="Gmail Logo" width={56} height={56} />
          </button>
          <span className="text-xs mt-2">Gmail</span>
        </div>

        {/* Calendar */}
        <div className="flex flex-col items-center">
          <button
            onClick={() => handleIntegrationClick?.('google-calendar')}
            className="bg-zinc-900 border border-zinc-700 shadow-md p-3 rounded-lg transition hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Connect Google Calendar"
            disabled={isIntegrating}
          >
            <Image src="/logos/calendar-logo.png" alt="Google Calendar Logo" width={56} height={56} />
          </button>
          <span className="text-xs mt-2">Calendar</span>
        </div>

        {/* LinkedIn */}
        <div className="flex flex-col items-center">
          <button
            onClick={() => handleIntegrationClick?.('linkedin')}
            className="bg-zinc-900 border border-zinc-700 shadow-md p-3 rounded-lg transition hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Connect LinkedIn"
            disabled={isIntegrating}
          >
            <Image src="/logos/linkedin-logo.svg" alt="LinkedIn Logo" width={56} height={56} />
          </button>
          <span className="text-xs mt-2">LinkedIn</span>
        </div>

        {/* X */}
        <div className="flex flex-col items-center">
          <button
            onClick={() => handleIntegrationClick?.('x')}
            className="bg-zinc-900 border border-zinc-700 shadow-md p-3 rounded-lg transition hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Connect X (Twitter)"
            disabled={isIntegrating}
          >
            <Image src="/logos/x-logo.svg" alt="X Logo" width={50} height={50} />
          </button>
          <span className="text-xs mt-2">X</span>
        </div>
      </div>
    </div>
  </>
);
