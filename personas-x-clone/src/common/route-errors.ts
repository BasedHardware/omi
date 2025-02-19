import HttpStatusCodes from '@src/common/HttpStatusCodes';


/******************************************************************************
                              Classes
******************************************************************************/

/**
 * Error with status code and message.
 */
export class RouteError extends Error {
  public status: HttpStatusCodes;

  public constructor(status: HttpStatusCodes, message: string) {
    super(message);
    this.status = status;
  }
}

/**
 * Validation in route layer errors.
 */
export class ValidationErr extends RouteError {
  public static MSG = 'One or more parameters were missing or invalid.';

  public constructor(errObj: unknown) {
    const msg = JSON.stringify({
      message: ValidationErr.MSG,
      parameters: errObj,
    });
    super(HttpStatusCodes.BAD_REQUEST, msg);
  }
}
