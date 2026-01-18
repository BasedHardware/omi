/**
 * Format large numbers into human-readable strings
 * @example formatInstalls(1500) => "1.5K"
 * @example formatInstalls(1500000) => "1.5M"
 */
export const formatInstalls = (num: number): string => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
};
