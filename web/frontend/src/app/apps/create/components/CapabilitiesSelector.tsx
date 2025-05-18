interface CapabilitiesSelectorProps {
  selectedCapabilities: string[];
  toggleCapability: (capabilityId: string) => void;
}

// Sample capabilities
const CAPABILITIES = [
  { id: 'chat', name: 'Chat' },
  { id: 'memories', name: 'Memories' },
  { id: 'proactive_notification', name: 'Notifications' },
  { id: 'external_integration', name: 'External Integration' },
];

export default function CapabilitiesSelector({
  selectedCapabilities,
  toggleCapability,
}: CapabilitiesSelectorProps) {
  return (
    <div className="mb-4">
      <label className="mb-2 block text-sm font-medium text-gray-300">
        App Capabilities
      </label>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {CAPABILITIES.map((capability) => (
          <div
            key={capability.id}
            onClick={() => toggleCapability(capability.id)}
            className={`cursor-pointer rounded-xl border p-3 text-center text-sm shadow-sm transition-colors hover:border-[#6C8EEF]/50 ${
              selectedCapabilities.includes(capability.id)
                ? 'border-[#6C8EEF] bg-[#6C8EEF]/10 text-[#6C8EEF]'
                : 'border-gray-700 bg-gray-800/50 text-gray-300'
            }`}
          >
            {capability.name}
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-gray-400">
        Select the capabilities your app will use
      </p>
    </div>
  );
}
