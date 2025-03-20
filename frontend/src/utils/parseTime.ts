import moment from 'moment';

type HourFormats = 'short' | 'long';

export const parseTime = (
  estimatedTime: string,
  format: HourFormats = 'short',
): string => {
  const duration = moment.duration(estimatedTime, 'minutes');
  const hours = duration.hours();
  const remainingMinutes = duration.minutes();

  const displayHourFormat = format === 'short' ? 'h' : `hour${hours > 1 ? 's' : ''}`;
  const displayMinutesFormat =
    format === 'short'
      ? 'm'
      : `minute${remainingMinutes > 1 || remainingMinutes === 0 ? 's' : ''}`;

  let result = '';

  if (hours > 0) {
    result += `${hours}${displayHourFormat} ${
      remainingMinutes > 0 ? remainingMinutes : ''
    }${remainingMinutes > 0 ? displayMinutesFormat : ''}`;
  }

  if (hours === 0) {
    result += `${remainingMinutes} ${displayMinutesFormat}`;
  }

  return result;
};
