/** Uniform widget mount point — the chat renders whichever widget matches
 *  the turn's discriminator. Keeps OnboardingChat.tsx small. */
import type { StepWidget, WidgetResult } from "../types";
import { ChipGroupWidget } from "./ChipGroup";
import { TextPromptCommitWidget } from "./TextPromptCommit";
import { PermissionGrantWidget } from "./PermissionGrant";
import { FileScanProgressWidget } from "./FileScanProgress";
import { ShortcutCaptureWidget } from "./ShortcutCapture";
import { ResearchPanelWidget } from "./ResearchPanel";
import { AcknowledgeWidget } from "./Acknowledge";

interface Props {
  widget: StepWidget;
  disabled: boolean;
  onCapture: (result: WidgetResult, summary: string | null) => void;
}

export function WidgetMount({ widget, disabled, onCapture }: Props) {
  switch (widget.type) {
    case "none":
      return null;
    case "chips":
      return (
        <ChipGroupWidget
          widget={widget}
          disabled={disabled}
          onCapture={onCapture}
        />
      );
    case "text_prompt":
      return (
        <TextPromptCommitWidget
          widget={widget}
          disabled={disabled}
          onCapture={onCapture}
        />
      );
    case "permission_grant":
      return (
        <PermissionGrantWidget
          widget={widget}
          disabled={disabled}
          onCapture={onCapture}
        />
      );
    case "file_scan_progress":
      return (
        <FileScanProgressWidget disabled={disabled} onCapture={onCapture} />
      );
    case "shortcut_capture":
      return (
        <ShortcutCaptureWidget
          widget={widget}
          disabled={disabled}
          onCapture={onCapture}
        />
      );
    case "research_panel":
      return <ResearchPanelWidget disabled={disabled} onCapture={onCapture} />;
    case "acknowledge":
      return (
        <AcknowledgeWidget
          widget={widget}
          disabled={disabled}
          onCapture={onCapture}
        />
      );
  }
}
