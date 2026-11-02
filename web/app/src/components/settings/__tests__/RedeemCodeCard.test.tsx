import { describe, expect, it } from 'vitest';
import { ApiHttpError } from '@/lib/api';
import { redeemErrorMessage, redeemedMessage } from '../RedeemCodeCard';

describe('redeem code messages', () => {
  it('says a full discount means no charge', () => {
    expect(redeemedMessage({ status: 'applied', percent_off: 100 })).toBe(
      "Code applied. You won't be charged.",
    );
    expect(redeemedMessage({ status: 'applied', percent_off: 20 })).toBe(
      'Code applied. 20% off your payment.',
    );
  });

  it('maps refusals to readable errors', () => {
    expect(redeemErrorMessage(new ApiHttpError(409, 'x'))).toMatch(/already been used/);
    expect(redeemErrorMessage(new ApiHttpError(400, 'x'))).toMatch(/can't be applied/);
    expect(redeemErrorMessage(new ApiHttpError(429, 'x'))).toMatch(/Too many tries/);
    expect(redeemErrorMessage(new Error('network'))).toMatch(/try again/);
  });
});
