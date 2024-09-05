'use client';
import { Fragment } from 'react';
import { Drawer, DrawerContent } from '@/src/components/ui/drawer';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Enlarge, Xmark } from 'iconoir-react';
import Link from 'next/link';
import { DialogTitle } from '../../ui/dialog';
import * as VisuallyHidden from '@radix-ui/react-visually-hidden';
import { ScrollArea } from '@/src/components/ui/scroll-area';

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
            <header className="relative z-20 flex w-full gap-2 px-4 pt-4 md:px-12 md:pt-12">
              <button
                onClick={() => handleOpen(false)}
                className="rounded-md p-1 hover:bg-zinc-800"
              >
                <Xmark className="text-base" />
              </button>
              <Link
                href={`/memories/${previewId}`}
                className="rounded-md p-1 hover:bg-zinc-800"
              >
                <Enlarge className="text-base" />
              </Link>
            </header>
            {children}
          </ScrollArea>
        </DrawerContent>
      </Drawer>
    </Fragment>
  );
}
