/** The parts of a React keydown event the composer needs to read. */
export interface ComposerKeyEvent {
  key: string;
  shiftKey: boolean;
  nativeEvent: { isComposing: boolean; keyCode?: number };
}

/**
 * Whether an Enter keypress should send the message.
 *
 * Enter pressed while an IME is composing commits the candidate text; it is
 * never the composer's send key. `KeyboardEvent.isComposing` reports that
 * state, and engines that predate it surface the composition keydown as
 * `keyCode` 229 instead, so both are checked.
 */
export function shouldSubmitComposerKey(event: ComposerKeyEvent): boolean {
  if (event.key !== 'Enter' || event.shiftKey) return false;
  return !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229;
}
