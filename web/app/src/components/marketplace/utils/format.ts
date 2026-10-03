import { formatLocale } from '@/lib/i18n';

/**
 * Format large numbers into human-readable strings
 * @example formatInstalls(1500) => "1.5K"
 * @example formatInstalls(1500000) => "1.5M"
 */
export const formatInstalls = (num: number): string => {
  if (num < 1000) {
    return num.toString();
  }

  return new Intl.NumberFormat(formatLocale(), {
    notation: 'compact',
    compactDisplay: 'short',
  }).format(num);
};
