import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/src/components/ui/accordion';

export default function Tendencies() {
  return (
    <Accordion type="single" collapsible defaultValue="item-1">
      <AccordionItem
        value="item-1"
        className="top-0 mb-5 rounded-md border border-solid border-neutral-800 bg-gradient-to-r from-[#030710] to-[#401c1c8c] text-white shadow-md shadow-[#06060742] transition-colors hover:border-neutral-700"
      >
        <AccordionTrigger className="p-3 text-base hover:no-underline md:p-5 md:text-lg">
          What's trending now!
        </AccordionTrigger>
        <AccordionContent className="p-3 md:p-5">
          <div className="flex flex-col gap-2">
            <div className="flex gap-2">
              <div className="fle-col flex h-20 w-1/2 flex-col justify-end rounded-lg bg-zinc-800/50 p-3">
                <h3 className="text-sm md:text-base">Work</h3>
                <p className="text-xs text-neutral-400 md:text-base">23 memories</p>
              </div>
              <div className="fle-col flex h-20 w-1/2 flex-col justify-end rounded-lg bg-zinc-800/50 p-3">
                <h3 className="text-sm md:text-base">Business</h3>
                <p className="text-xs text-neutral-400 md:text-base">6 memories</p>
              </div>
            </div>
            <div className="flex gap-2">
              <div className="fle-col flex h-20 w-1/2 flex-col justify-end rounded-lg bg-zinc-800/50 p-3">
                <h3 className="text-sm md:text-base">Inspiration</h3>
                <p className="text-xs text-neutral-400 md:text-base">6 memories</p>
              </div>
              <div className="fle-col flex h-20 w-1/2 flex-col justify-end rounded-lg bg-zinc-800/50 p-3">
                <h3 className="text-sm md:text-base">Social</h3>
                <p className="text-xs text-neutral-400 md:text-base">6 memories</p>
              </div>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
