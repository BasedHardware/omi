/**
 * Pop-out window utilities for recording widgets
 */

interface PopoutOptions {
  width: number;
  height: number;
  title: string;
}

/**
 * Opens a new pop-out window with the specified path and options.
 * Window appears in the top-right area of the screen.
 */
export function openPopoutWindow(
  path: string,
  options: PopoutOptions
): Window | null {
  const { width, height, title } = options;

  // Position in top-right area of screen
  const left = window.screenX + window.outerWidth - width - 20;
  const top = window.screenY + 100;

  const features = [
    `width=${width}`,
    `height=${height}`,
    `left=${left}`,
    `top=${top}`,
    'menubar=no',
    'toolbar=no',
    'location=no',
    'status=no',
    'resizable=yes',
    'scrollbars=yes',
  ].join(',');

  return window.open(path, title, features);
}

/**
 * Opens the compact recording widget pop-out
 */
export function openRecordingWidget(): Window | null {
  return openPopoutWindow('/record/popout', {
    width: 280,
    height: 100,
    title: 'omi-recording-widget',
  });
}

/**
 * Opens the full transcript pop-out window
 */
export function openTranscriptWindow(): Window | null {
  return openPopoutWindow('/record/popout/transcript', {
    width: 480,
    height: 600,
    title: 'omi-recording-transcript',
  });
}
