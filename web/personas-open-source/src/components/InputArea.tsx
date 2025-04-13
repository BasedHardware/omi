/**
 * @fileoverview InputArea Component for OMI Personas
 * @description Renders the input field and button for creating new AI personas
 * @author HarshithSunku
 * @license MIT
 */
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

interface InputAreaProps {
  handle: string;
  handleInputChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleCreatePersona: (inputHandle?: string) => void;
  isCreating: boolean;
}

export const InputArea: React.FC<InputAreaProps> = ({ handle, handleInputChange, handleCreatePersona, isCreating }) => (
  <>
    {/* Create Section */}
    <div className="text-center max-w-md mx-auto mb-8">
      <h1 className="text-4xl md:text-5xl font-serif mb-3 md:mb-4">Your Personal AI</h1>
      <p className="text-gray-400 text-sm md:text-base mb-8 md:mb-12">
      Train an AI based on your Twitter or Linkedin
      </p>
    </div>
    
    <div className="w-full max-w-sm space-y-4 mb-12 md:mb-16">
      <Input
        type="text"
        placeholder="Enter Twitter/Linkedin handle (e.g., @elonmusk)..."
        value={handle}
        onChange={handleInputChange}
        className="rounded-full bg-gray-800 text-white border-gray-700 focus:border-gray-600 text-lg py-3"
      />
      <Button
        className="w-full rounded-full bg-white text-black hover:bg-gray-200"
        onClick={() => handleCreatePersona(handle)}
        disabled={isCreating}
      >
        {isCreating ? 'Creating...' : 'Train Personal AI'}
      </Button>
    </div>
  </>
);
