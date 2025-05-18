interface PrivacySettingsProps {
  isPublic: boolean;
  setIsPublic: (isPublic: boolean) => void;
  termsAgreed: boolean;
  setTermsAgreed: (agreed: boolean) => void;
}

export default function PrivacySettings({
  isPublic,
  setIsPublic,
  termsAgreed,
  setTermsAgreed,
}: PrivacySettingsProps) {
  return (
    <div className="mb-6 space-y-4">
      <div>
        <label className="mb-2 block text-sm font-medium text-gray-300">
          Visibility
        </label>
        <div className="flex space-x-4">
          <div
            className={`cursor-pointer rounded-xl border p-3 text-center text-sm shadow-sm transition-colors hover:border-[#6C8EEF]/50 ${
              isPublic
                ? 'border-[#6C8EEF] bg-[#6C8EEF]/10 text-[#6C8EEF]'
                : 'border-gray-700 bg-gray-800/50 text-gray-300'
            }`}
            onClick={() => setIsPublic(true)}
            role="radio"
            aria-checked={isPublic}
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                setIsPublic(true);
              }
            }}
          >
            Public (Listed in App Store)
          </div>
          <div
            className={`cursor-pointer rounded-xl border p-3 text-center text-sm shadow-sm transition-colors hover:border-[#6C8EEF]/50 ${
              !isPublic
                ? 'border-[#6C8EEF] bg-[#6C8EEF]/10 text-[#6C8EEF]'
                : 'border-gray-700 bg-gray-800/50 text-gray-300'
            }`}
            onClick={() => setIsPublic(false)}
            role="radio"
            aria-checked={!isPublic}
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                setIsPublic(false);
              }
            }}
          >
            Private (Shareable Link Only)
          </div>
        </div>
      </div>

      <div className="flex items-start">
        <div className="flex h-5 items-center">
          <input
            id="terms"
            type="checkbox"
            checked={termsAgreed}
            onChange={(e) => setTermsAgreed(e.target.checked)}
            className="h-4 w-4 rounded border-gray-600 bg-gray-700 text-[#6C2BD9] focus:ring-2 focus:ring-[#6C2BD9]"
            required
          />
        </div>
        <label
          htmlFor="terms"
          className="ml-2 text-sm text-gray-300"
        >
          I agree to the{' '}
          <a href="#" className="text-[#6C8EEF] hover:underline">
            Terms of Service
          </a>{' '}
          and{' '}
          <a href="#" className="text-[#6C8EEF] hover:underline">
            Community Guidelines
          </a>
        </label>
      </div>
    </div>
  );
}
