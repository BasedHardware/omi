/**
 * Which mode Home rests in, ported from the desktop app's
 * `HomeStagePresentation.restingMode` (macOS `DashboardPage`).
 *
 * Home is the only chat surface on both clients, so this rule is what decides
 * whether you land on the hub or straight in the transcript.
 */

export type HomeStageMode = 'hub' | 'chat';

export interface HomeStageInputs {
  isLoading: boolean;
  hasMeaningfulHistory: boolean;
  /**
   * A send in flight counts as chat: the stage must move on the first message
   * rather than waiting for the reply to land, or the hub would flash back.
   */
  isStreaming: boolean;
}

export function restingMode({
  isLoading,
  hasMeaningfulHistory,
  isStreaming,
}: HomeStageInputs): HomeStageMode {
  if (isStreaming) return 'chat';
  // While history is still loading the count is not yet a fact about the
  // account, so the hub holds rather than flashing an empty transcript.
  return !isLoading && hasMeaningfulHistory ? 'chat' : 'hub';
}
