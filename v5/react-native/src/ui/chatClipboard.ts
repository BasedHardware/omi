import {Platform, Share} from 'react-native';
import {omiBackend} from '../omiNative';

export type ChatCopyResult = 'copied' | 'shared' | 'dismissed';

/** Phones have no clipboard module yet: they copy through the share sheet. */
export function chatCopySharesOnPhone(): boolean {
  return Platform.OS === 'ios' || Platform.OS === 'android';
}

/**
 * Copies chat text: the native desktop clipboard command, the browser
 * clipboard on web, and the system share sheet (which offers Copy) on
 * phones. Throws when no route exists so callers can say so.
 */
export async function copyChatText(text: string): Promise<ChatCopyResult> {
  if (omiBackend?.copyToClipboard) {
    await omiBackend.copyToClipboard(text);
    return 'copied';
  }
  if (typeof navigator !== 'undefined' && 'clipboard' in navigator) {
    await (
      navigator as Navigator & {
        clipboard: {writeText(value: string): Promise<void>};
      }
    ).clipboard.writeText(text);
    return 'copied';
  }
  if (chatCopySharesOnPhone()) {
    const result = await Share.share({message: text});
    return result.action === Share.dismissedAction ? 'dismissed' : 'shared';
  }
  throw new Error('Clipboard unavailable');
}
