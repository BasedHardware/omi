/**
 * @fileoverview InputArea Component for OMI Personas
 * @description Renders the input field and button for creating new AI personas
 * @author HarshithSunku
 * @license MIT
 */
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

/**
 * InputArea Component
 * 
 * @component
 * @description Renders an input field for social media handles and a create button
 * @param {Object} props - Component props
 * @param {string} props.handle - Current input value
 * @param {Function} props.handleInputChange - Input change handler
 * @param {Function} props.handleCreatePersona - Create persona button click handler
 * @param {boolean} props.isCreating - Loading state for persona creation
 * @returns {JSX.Element} Rendered InputArea component
 */
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
