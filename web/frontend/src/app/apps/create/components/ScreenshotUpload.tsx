import { Plus, Trash2 } from 'lucide-react';
import Image from 'next/image';

interface ScreenshotUploadProps {
  screenshots: string[];
  setScreenshots: (screenshots: string[]) => void;
}

export default function ScreenshotUpload({
  screenshots,
  setScreenshots,
}: ScreenshotUploadProps) {
  // Handle screenshot upload
  const handleScreenshotUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.onload = (e) => {
        if (e.target?.result) {
          setScreenshots([...screenshots, e.target.result as string]);
        }
      };
      reader.readAsDataURL(file);
    }
  };

  // Remove screenshot
  const removeScreenshot = (index: number) => {
    setScreenshots(screenshots.filter((_, i) => i !== index));
  };

  return (
    <div className="mb-4">
      <label className="mb-2 block text-sm font-medium text-gray-300">
        Screenshots
      </label>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
        {screenshots.map((screenshot, index) => (
          <div
            key={index}
            className="relative aspect-[9/16] overflow-hidden rounded-lg border border-gray-700 shadow-md"
          >
            <Image
              src={screenshot}
              alt={`Screenshot ${index + 1}`}
              fill
              className="object-cover"
            />
            <button
              type="button"
              onClick={() => removeScreenshot(index)}
              className="absolute right-2 top-2 rounded-full bg-red-500 p-1.5 shadow-md transition-transform hover:scale-105"
            >
              <Trash2 className="h-3.5 w-3.5 text-white" />
            </button>
          </div>
        ))}

        {screenshots.length < 5 && (
          <div className="group aspect-[9/16] cursor-pointer rounded-lg border border-dashed border-gray-700 bg-gray-800/50 transition-all hover:border-[#6C8EEF]/50 hover:bg-gray-800">
            <label
              htmlFor="screenshot-upload"
              className="flex h-full w-full cursor-pointer flex-col items-center justify-center"
            >
              <Plus className="mb-1 h-6 w-6 text-gray-400 transition-colors group-hover:text-[#6C8EEF]" />
              <span className="text-xs text-gray-400 transition-colors group-hover:text-[#6C8EEF]">
                Add Screenshot
              </span>
            </label>
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleScreenshotUpload}
              id="screenshot-upload"
            />
          </div>
        )}
      </div>
      <p className="mt-2 text-xs text-gray-400">
        Add up to 5 screenshots showing your app in action
      </p>
    </div>
  );
}
