import { ChevronDownIcon } from "lucide-react";
import { Accordion as AccordionPrimitive } from "radix-ui";
import { Accordion as ShadcnAccordion } from "../../ui/accordion";
import { Card, CardContent } from "../../ui/card";
import { cn } from "../../../lib/utils";
import type { AccordionData } from "../types";
import { GenerativeMarkdown } from "../GenerativeMarkdown";

export function Accordion({ data }: { data: AccordionData }) {
  const items = data.items.map((item, i) => (
    <AccordionPrimitive.Item
      key={i}
      value={`item-${i}`}
      className={cn(
        "border-b border-border/40 last:border-b-0",
      )}
    >
      <AccordionPrimitive.Header className="flex">
        <AccordionPrimitive.Trigger
          className={cn(
            "group flex flex-1 items-center justify-between gap-3 px-5 py-4 text-left text-sm font-medium text-foreground transition-colors outline-none",
            "hover:bg-accent/40 focus-visible:bg-accent/40",
          )}
        >
          <span className="truncate">{item.title}</span>
          <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-data-[state=open]:rotate-180" />
        </AccordionPrimitive.Trigger>
      </AccordionPrimitive.Header>
      <AccordionPrimitive.Content
        className={cn(
          "overflow-hidden text-sm",
          "data-[state=closed]:hidden data-[state=open]:animate-accordion-down",
        )}
      >
        <div className="px-5 pb-3 pt-1">
          <GenerativeMarkdown
            content={item.content}
            className="prose-sm max-w-none text-muted-foreground"
          />
        </div>
      </AccordionPrimitive.Content>
    </AccordionPrimitive.Item>
  ));

  const body = data.allowMultiple ? (
    <ShadcnAccordion type="multiple">{items}</ShadcnAccordion>
  ) : (
    <ShadcnAccordion type="single" collapsible>
      {items}
    </ShadcnAccordion>
  );

  return (
    <Card className="not-prose my-3 gap-0 overflow-hidden border-border/60 py-0">
      {data.title && (
        <div className="flex items-center justify-between border-b border-border/40 px-5 py-2.5">
          <p className="text-sm font-semibold text-foreground">{data.title}</p>
          <p className="text-xs text-muted-foreground">
            {data.items.length} {data.items.length === 1 ? "section" : "sections"}
          </p>
        </div>
      )}
      <CardContent className="p-0">{body}</CardContent>
    </Card>
  );
}
