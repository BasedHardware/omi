import { AuthProvider } from '@/components/auth/AuthProvider';
import { RecordingProvider, RecordingController } from '@/components/recording';
import { ToastProvider } from '@/components/ui/Toast';
import { PublicBuildCanary } from '@/components/public-build-canary';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="dark bg-bg-primary text-text-primary font-body antialiased overflow-x-hidden w-full">
        <PublicBuildCanary />
        <AuthProvider>
          <RecordingProvider>
            <ToastProvider>
              <RecordingController />
              {children}
            </ToastProvider>
          </RecordingProvider>
        </AuthProvider>
      </div>
    </>
  );
}
