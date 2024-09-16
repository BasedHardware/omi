'use client';
import { Fragment } from 'react';
import { Drawer, DrawerContent } from '@/src/components/ui/drawer';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { DialogTitle } from '../../ui/dialog';
import * as VisuallyHidden from '@radix-ui/react-visually-hidden';
import { ScrollArea } from '@/src/components/ui/scroll-area';
import SidePanelHeader from './side-panel-header';

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
    if (value && previewId) {
      urlParams.set('previewId', previewId);
    } else {
      urlParams.delete('previewId');
    }
    router.push(`${pathname}?${urlParams.toString()}`, { scroll: false });
  };

  return (
    <Fragment>
      <Drawer
        disablePreventScroll={false}
        direction="right"
        open={!!previewId}
        onOpenChange={handleOpen}
      >
        <DrawerContent
          aria-describedby={undefined}
          className="ml-auto max-w-screen-md overflow-hidden text-white"
        >
          <VisuallyHidden.Root>
            <DialogTitle>Memory Details</DialogTitle>
          </VisuallyHidden.Root>
          <ScrollArea className="h-screen max-h-screen select-text bg-zinc-900">
            <SidePanelHeader handleOpen={handleOpen} previewId={previewId} />
            {children}
          </ScrollArea>
        </DrawerContent>
      </Drawer>
    </Fragment>
  );
}
