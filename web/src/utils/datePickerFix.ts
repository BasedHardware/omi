/**
 * OMI Web App - Timezone-aware Date Picker Utility
 * Issue #15248: Fix date picker showing wrong day near midnight timezone offset
 * Author: Hasnain Chavhan (@HasnainChavhan)
 */

export function getLocalMidnightISOString(dateInput: Date | string): string {
  const d = new Date(dateInput);
  // Ensure local timezone offset is preserved rather than converting to UTC midnight
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function isValidDueDate(dueDate: string): boolean {
  if (!dueDate) return false;
  const target = new Date(dueDate);
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return target >= now;
}
