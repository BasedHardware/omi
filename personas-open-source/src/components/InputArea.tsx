import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

interface InputAreaProps {
  handle: string;
  handleInputChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  handleCreatePersona: () => void;
  isCreating: boolean;
}

export const InputArea: React.FC<InputAreaProps> = ({ handle, handleInputChange, handleCreatePersona, isCreating }) => (
  <div className="w-full max-w-sm space-y-4 mb-12 md:mb-16">
    <Input
      type="text"
      placeholder="Enter Twitter/Linkedin handle (e.g., @elonmusk)..."
      value={handle}
      onChange={handleInputChange}
      className="rounded-full bg-gray-800 text-white border-gray-700 focus:border-gray-600 text-lg py-3"
    />
    <Button
      className="w-full rounded-full bg-white text-black hover:bg-gray-200 text-lg py-3"
      onClick={handleCreatePersona}
      disabled={isCreating}
    >
      {isCreating ? 'Creating...' : 'Create AI Persona'}
    </Button>
  </div>
);
