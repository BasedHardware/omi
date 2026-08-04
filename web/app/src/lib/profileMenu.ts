/**
 * Ceiling for the profile menu's open transition, in pixels.
 *
 * A ceiling rather than `height: auto` so the open state needs no measurement.
 * It must stay above the menu's real height or the last row is silently
 * clipped, so `profileMenuHeightBound` derives that height from the row count
 * and a test holds the two together.
 */
export const PROFILE_MENU_MAX_HEIGHT = 520;

/**
 * The tallest the profile menu can be: one row each for Connectors, the
 * settings sections, the four support links (Download, Help, Feedback,
 * Discord) and Sign Out, plus the two groups' padding and the divider between
 * them.
 */
export function profileMenuHeightBound(sectionCount: number): number {
  const rows = 1 + sectionCount + 4 + 1;
  return rows * MENU_ROW_HEIGHT + 2 * MENU_GROUP_PADDING + MENU_DIVIDER;
}

/** py-2 text-sm row: 36px of content plus the 2px gap below it. */
const MENU_ROW_HEIGHT = 38;
/** p-2 top and bottom on each of the two groups. */
const MENU_GROUP_PADDING = 16;
const MENU_DIVIDER = 1;
