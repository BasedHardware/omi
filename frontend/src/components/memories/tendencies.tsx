import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/src/components/ui/accordion';
import TrendingItem from './tendencies/trending-item';

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
              <TrendingItem title='work' count={23} />
              <TrendingItem title='Business' count={6} />
            </div>
            <div className="flex gap-2">
              <TrendingItem title='Inspiration' count={6} />
              <TrendingItem title='Social' count={6} />
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
