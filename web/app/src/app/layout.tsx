import { AuthProvider } from '@/components/auth/AuthProvider';
import { MobileBlockOverlay } from '@/components/layout/MobileBlockOverlay';
import { RecordingProvider, RecordingController } from '@/components/recording';
import { ToastProvider } from '@/components/ui/Toast';
import { PublicBuildCanary } from '@/components/public-build-canary';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="dark bg-bg-primary text-text-primary font-body antialiased overflow-x-hidden w-full">
        <PublicBuildCanary />
        <MobileBlockOverlay />
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
