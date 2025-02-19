import { IReqPropErr } from '@src/routes/common';
import UserRepo from '@src/repos/UserRepo';


/******************************************************************************
                                Types
******************************************************************************/

export interface IValidationErr {
  message: string;
  parameters: IReqPropErr[];
}


/******************************************************************************
                                Functions
******************************************************************************/

/**
 * Delete all records for unit testing.
 */
export async function cleanDatabase(): Promise<void> {
  await Promise.all([
    UserRepo.deleteAllUsers(),
  ]);
}
