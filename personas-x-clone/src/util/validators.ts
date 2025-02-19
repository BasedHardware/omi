import { isNumber } from 'jet-validators';


/**
 * Database relational key.
 */
export function isRelationalKey(arg: unknown): arg is number {
  return isNumber(arg) && arg >= -1;
}
