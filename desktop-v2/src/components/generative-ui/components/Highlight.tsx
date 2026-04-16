import { InfoIcon } from "lucide-react";
import { Alert, AlertDescription } from "../../ui/alert";
import type { HighlightData } from "../types";

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const h = hex.replace(/^#/, "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

export function Highlight({ data }: { data: HighlightData }) {
  const { r, g, b } = hexToRgb(data.color);
  const tint = (a: number) => `rgba(${r}, ${g}, ${b}, ${a})`;

  return (
    <Alert
      className="not-prose my-3"
      style={{
        borderColor: tint(0.3),
        backgroundColor: tint(0.08),
        color: "hsl(var(--foreground))",
      }}
    >
      <InfoIcon style={{ color: data.color }} />
      <AlertDescription className="text-foreground">
        {data.text}
      </AlertDescription>
    </Alert>
  );
}
