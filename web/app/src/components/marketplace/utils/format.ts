/**
 * Format large numbers into human-readable strings
 * @example formatInstalls(1500) => "1.5K"
 * @example formatInstalls(1500000) => "1.5M"
 */
export const formatInstalls = (num: number): string => {
  if (num < 1000) {
    return num.toString();
  }

  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    compactDisplay: 'short',
  }).format(num);
};
