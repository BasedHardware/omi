import { Response, Request } from 'express';
import { isObject, isString } from 'jet-validators';
import { parseObject, TSchema } from 'jet-validators/utils';

import { ValidationErr } from '@src/common/route-errors';


/******************************************************************************
                                Types
******************************************************************************/

type TRecord = Record<string, unknown>;
export type IReq = Request<TRecord, void, TRecord, TRecord>;
export type IRes = Response<unknown, TRecord>;

export interface IReqPropErr {
  prop: string;
  value: unknown;
  moreInfo?: string;
}


/******************************************************************************
                                Functions
******************************************************************************/

/**
 * Parse a Request object property and throw a Validation error if it fails.
 */
export function parseReq<U extends TSchema>(schema: U) {
  return (arg: unknown) => {
    // Don't alter original object
    if (isObject(arg)) {
      arg = { ...arg };
    }
    // Error callback
    const errArr: IReqPropErr[] = [];
    const errCb = (
      prop = 'undefined',
      value?: unknown,
      caughtErr?: unknown,
    ) => {
      const err: IReqPropErr = { prop, value };
      if (caughtErr !== undefined) {
        let moreInfo;
        if (!isString(caughtErr)) {
          moreInfo = JSON.stringify(caughtErr);
        } else {
          moreInfo = caughtErr;
        }
        err.moreInfo = moreInfo;
      }
      errArr.push(err);
    };
    // Return
    const retVal = parseObject<U>(schema, errCb)(arg);
    if (errArr.length > 0) {
      throw new ValidationErr(errArr);
    }
    return retVal;
  };
}
