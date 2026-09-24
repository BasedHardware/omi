import { Request, Response } from 'express';
import { storeAuthCode } from '../services/authStorage';
import { generateAuthUrl } from '../utils/oauth';

export const authHandler = async (req: Request, res: Response) => {
  try {
    // Existing logic to generate auth URL and redirect
    const authUrl = generateAuthUrl();
    // Store state in DB
    await storeAuthCode(req.query.state as string);
    res.redirect(authUrl);
  } catch (e) {
    // Log the raw error for debugging but do not expose it to the client
    console.error('[Google Calendar Auth] Unexpected error:', e);
    res.status(500).send('Internal Server Error');
  }
};
