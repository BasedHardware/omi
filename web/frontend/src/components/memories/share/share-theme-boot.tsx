import { SHARE_THEME_BOOT_SCRIPT } from '@/src/lib/share-theme.mjs';

/** Applies a saved light/dark choice before the note paints. Render it above `.share-note`. */
export default function ShareThemeBoot() {
  return <script dangerouslySetInnerHTML={{ __html: SHARE_THEME_BOOT_SCRIPT }} />;
}
