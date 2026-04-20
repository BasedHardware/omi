import type { ComponentType } from "react";
import { Activity, BarChart3, FileText, Lightbulb, Monitor } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { INSIGHT_CATEGORY_LABEL, type StoredInsight } from "@/stores/insightStore";
import { formatRelative } from "./formatRelative";

interface Props {
  insight: StoredInsight | null;
  categoryIcon: ComponentType<{ size?: number; className?: string }>;
  onClose: () => void;
}

export function InsightDetailSheet({
  insight,
  categoryIcon: Icon,
  onClose,
}: Props) {
  const open = insight !== null;

  return (
    <Dialog open={open} onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent className="insight-detail-sheet sm:max-w-md">
        {insight ? (
          <>
            <DialogHeader className="insight-detail-header">
              <div className="insight-detail-category">
                <Icon size={14} />
                <span>{INSIGHT_CATEGORY_LABEL[insight.category]}</span>
              </div>
              <DialogTitle className="insight-detail-title">
                {insight.content}
              </DialogTitle>
            </DialogHeader>

            {insight.reasoning && (
              <section className="insight-detail-section">
                <header className="insight-detail-section-title">
                  <Lightbulb size={12} />
                  <span>Why this insight?</span>
                </header>
                <p className="insight-detail-section-body">
                  {insight.reasoning}
                </p>
              </section>
            )}

            <section className="insight-detail-section">
              <header className="insight-detail-section-title">
                <FileText size={12} />
                <span>Context</span>
              </header>
              <ul className="insight-detail-context">
                <li>
                  <Monitor size={12} />
                  <span>{insight.sourceApp}</span>
                </li>
                {insight.currentActivity && (
                  <li>
                    <Activity size={12} />
                    <span>{insight.currentActivity}</span>
                  </li>
                )}
                {insight.contextSummary && (
                  <li>
                    <FileText size={12} />
                    <span>{insight.contextSummary}</span>
                  </li>
                )}
              </ul>
            </section>

            <footer className="insight-detail-footer">
              <span className="insight-detail-footer-item">
                <BarChart3 size={11} />
                {Math.round(insight.confidence * 100)}% confidence
              </span>
              <span className="insight-detail-footer-spacer" />
              <span className="insight-detail-footer-item">
                {formatRelative(insight.createdAt)}
              </span>
            </footer>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
