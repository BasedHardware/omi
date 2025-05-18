interface PromptFieldsProps {
  selectedCapabilities: string[];
  chatPrompt: string;
  setChatPrompt: (prompt: string) => void;
  memoryPrompt: string;
  setMemoryPrompt: (prompt: string) => void;
}

export default function PromptFields({
  selectedCapabilities,
  chatPrompt,
  setChatPrompt,
  memoryPrompt,
  setMemoryPrompt,
}: PromptFieldsProps) {
  return (
    <div className="space-y-4">
      {selectedCapabilities.includes('chat') && (
        <div>
          <label
            htmlFor="chatPrompt"
            className="mb-2 block text-sm font-medium text-gray-300"
          >
            Chat Prompt
          </label>
          <textarea
            id="chatPrompt"
            value={chatPrompt}
            onChange={(e) => setChatPrompt(e.target.value)}
            placeholder="Provide instructions for how your app should respond to chat messages..."
            rows={4}
            className="w-full rounded-xl border border-gray-700 bg-gray-800/50 p-2.5 text-white shadow-sm transition-colors focus:border-[#6C8EEF]/50 focus:outline-none focus:ring-1 focus:ring-[#6C8EEF]/50"
            required={selectedCapabilities.includes('chat')}
          />
          <p className="mt-1 text-xs text-gray-400">
            This is the prompt your app will use to respond to messages.
          </p>
        </div>
      )}

      {selectedCapabilities.includes('memories') && (
        <div>
          <label
            htmlFor="memoryPrompt"
            className="mb-2 block text-sm font-medium text-gray-300"
          >
            Memory Processing Prompt
          </label>
          <textarea
            id="memoryPrompt"
            value={memoryPrompt}
            onChange={(e) => setMemoryPrompt(e.target.value)}
            placeholder="Provide instructions for how your app should process and respond to memories..."
            rows={4}
            className="w-full rounded-xl border border-gray-700 bg-gray-800/50 p-2.5 text-white shadow-sm transition-colors focus:border-[#6C8EEF]/50 focus:outline-none focus:ring-1 focus:ring-[#6C8EEF]/50"
            required={selectedCapabilities.includes('memories')}
          />
          <p className="mt-1 text-xs text-gray-400">
            This is the prompt your app will use to process memory data.
          </p>
        </div>
      )}
    </div>
  );
}
