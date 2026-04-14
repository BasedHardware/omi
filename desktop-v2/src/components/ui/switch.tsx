import * as React from "react";
import { Switch as SwitchPrimitive } from "radix-ui";

export const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className = "", ...props }, ref) => (
  <SwitchPrimitive.Root
    ref={ref}
    className={[
      "peer inline-flex h-[18px] w-[30px] shrink-0 cursor-pointer items-center rounded-full",
      "border border-transparent transition-colors",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
      "disabled:cursor-not-allowed disabled:opacity-50",
      "data-[state=checked]:bg-green-500 data-[state=unchecked]:bg-muted-foreground/30",
      className,
    ].join(" ")}
    {...props}
  >
    <SwitchPrimitive.Thumb
      className={[
        "pointer-events-none block h-3.5 w-3.5 rounded-full bg-white shadow-sm ring-0",
        "transition-transform",
        "data-[state=checked]:translate-x-[13px] data-[state=unchecked]:translate-x-[1px]",
      ].join(" ")}
    />
  </SwitchPrimitive.Root>
));
Switch.displayName = "Switch";
