'use client';
import { Fragment } from 'react';
import { Drawer, DrawerContent } from '@/src/components/ui/drawer';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

interface SidePanelWrapperProps {
  children: React.ReactNode;
  previewId: string | undefined;
}

export default function SidePanelWrapper({ children, previewId }: SidePanelWrapperProps) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const handleOpen = (value: boolean) => {
    const urlParams = new URLSearchParams(searchParams);
    if(value && previewId) {
      urlParams.set('previewId', previewId);
    } else {
      urlParams.delete('previewId');
    }
    router.push(`${pathname}?${urlParams.toString()}`, { scroll: false });
  }

  return (
    <Fragment>
      <Drawer
        preventScrollRestoration
        direction="right"
        open={!!previewId}
        onOpenChange={handleOpen}
      >
        <DrawerContent className="ml-auto min-h-screen max-w-screen-md bg-zinc-900 text-white">
          {children}
        </DrawerContent>
      </Drawer>
    </Fragment>
  );
}
