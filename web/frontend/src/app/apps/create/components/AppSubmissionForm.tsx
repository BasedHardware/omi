'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import AppIconUpload from './AppIconUpload';
import ScreenshotUpload from './ScreenshotUpload';
import CategorySelector from './CategorySelector';
import CapabilitiesSelector from './CapabilitiesSelector';
import PricingSection from './PricingSection';
import PromptFields from './PromptFields';
import PrivacySettings from './PrivacySettings';

export default function AppSubmissionForm() {
  // Form state
  const [appName, setAppName] = useState('');
  const [appDescription, setAppDescription] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [appIcon, setAppIcon] = useState<File | null>(null);
  const [appIconPreview, setAppIconPreview] = useState<string | null>(null);
  const [isPaid, setIsPaid] = useState(false);
  const [price, setPrice] = useState('');
  const [screenshots, setScreenshots] = useState<string[]>([]);
  const [selectedCapabilities, setSelectedCapabilities] = useState<string[]>([]);
  const [chatPrompt, setChatPrompt] = useState('');
  const [memoryPrompt, setMemoryPrompt] = useState('');
  const [isPublic, setIsPublic] = useState(true);
  const [termsAgreed, setTermsAgreed] = useState(false);

  // Toggle capability selection
  const toggleCapability = (capabilityId: string) => {
    if (selectedCapabilities.includes(capabilityId)) {
      setSelectedCapabilities(selectedCapabilities.filter((id) => id !== capabilityId));
    } else {
      setSelectedCapabilities([...selectedCapabilities, capabilityId]);
    }
  };

  // Form validation
  const isFormValid =
    appName.trim() !== '' &&
    appDescription.trim() !== '' &&
    selectedCategory !== '' &&
    appIcon !== null &&
    screenshots.length > 0 &&
    selectedCapabilities.length > 0 &&
    termsAgreed &&
    (selectedCapabilities.includes('chat') ? chatPrompt.trim() !== '' : true) &&
    (selectedCapabilities.includes('memories') ? memoryPrompt.trim() !== '' : true);

  // Handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isFormValid) return;

    // Here you would typically send the data to your API
    alert('App submitted for review!');
  };

  return (
    <main className="min-h-screen bg-[#0B0F17] pb-20 pt-24">
      <div className="container mx-auto px-4">
        <div className="mb-8">
          <Link
            href="/apps"
            className="flex items-center text-sm text-[#6C8EEF] hover:underline"
          >
            <ArrowLeft className="mr-1 h-4 w-4" />
            Back to Apps
          </Link>
        </div>

        <div className="mx-auto max-w-3xl">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">Create Your App</h1>
            <p className="mt-2 text-gray-400">
              Build and share your own AI-powered app for Omi
            </p>
          </div>

          <div className="mb-6 rounded-xl bg-gray-800 p-4 shadow-sm">
            <Link
              href="https://docs.omi.me/docs/developer/apps/Introduction"
              target="_blank"
              className="block text-center text-[#6C8EEF] hover:underline"
            >
              Want to build an app but not sure where to begin? Click here!
            </Link>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* App Metadata */}
            <div className="rounded-xl bg-gray-900 p-6 shadow-sm">
              <h2 className="mb-4 text-xl font-bold text-white">App Information</h2>

              <AppIconUpload
                appIcon={appIcon}
                setAppIcon={setAppIcon}
                appIconPreview={appIconPreview}
                setAppIconPreview={setAppIconPreview}
              />

              <div className="mb-4">
                <label
                  htmlFor="appName"
                  className="mb-2 block text-sm font-medium text-gray-300"
                >
                  App Name
                </label>
                <input
                  type="text"
                  id="appName"
                  value={appName}
                  onChange={(e) => setAppName(e.target.value)}
                  className="w-full rounded-xl border border-gray-700 bg-gray-800/50 p-2.5 text-white shadow-sm transition-colors focus:border-[#6C8EEF]/50 focus:outline-none focus:ring-1 focus:ring-[#6C8EEF]/50"
                  placeholder="MyAwesomeApp"
                  required
                />
              </div>

              <div className="mb-4">
                <label
                  htmlFor="appDescription"
                  className="mb-2 block text-sm font-medium text-gray-300"
                >
                  App Description
                </label>
                <textarea
                  id="appDescription"
                  value={appDescription}
                  onChange={(e) => setAppDescription(e.target.value)}
                  className="w-full rounded-xl border border-gray-700 bg-gray-800/50 p-2.5 text-white shadow-sm transition-colors focus:border-[#6C8EEF]/50 focus:outline-none focus:ring-1 focus:ring-[#6C8EEF]/50"
                  placeholder="Describe what your app does and how it works..."
                  rows={5}
                  required
                />
              </div>

              <CategorySelector
                selectedCategory={selectedCategory}
                setSelectedCategory={setSelectedCategory}
              />

              <ScreenshotUpload
                screenshots={screenshots}
                setScreenshots={setScreenshots}
              />
            </div>

            {/* App Functionality */}
            <div className="rounded-xl bg-gray-900 p-6 shadow-sm">
              <h2 className="mb-4 text-xl font-bold text-white">App Functionality</h2>

              <CapabilitiesSelector
                selectedCapabilities={selectedCapabilities}
                toggleCapability={toggleCapability}
              />

              <PromptFields
                selectedCapabilities={selectedCapabilities}
                chatPrompt={chatPrompt}
                setChatPrompt={setChatPrompt}
                memoryPrompt={memoryPrompt}
                setMemoryPrompt={setMemoryPrompt}
              />
            </div>

            {/* App Distribution */}
            <div className="rounded-xl bg-gray-900 p-6 shadow-sm">
              <h2 className="mb-4 text-xl font-bold text-white">App Distribution</h2>

              <PricingSection
                isPaid={isPaid}
                setIsPaid={setIsPaid}
                price={price}
                setPrice={setPrice}
              />

              <PrivacySettings
                isPublic={isPublic}
                setIsPublic={setIsPublic}
                termsAgreed={termsAgreed}
                setTermsAgreed={setTermsAgreed}
              />
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={!isFormValid}
                className={`rounded-xl px-6 py-2.5 font-medium text-white shadow-sm ${
                  isFormValid
                    ? 'bg-[#6C2BD9] hover:bg-[#5A1CB8]'
                    : 'cursor-not-allowed bg-gray-700 opacity-70'
                }`}
              >
                Submit App for Review
              </button>
            </div>
          </form>
        </div>
      </div>
    </main>
  );
}
