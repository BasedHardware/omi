import { Router, Request, Response } from 'express';
import { logger } from '../../utils/logger';
import { getOAuthState, storeOAuthState } from './state';
import { buildAuthUrl, exchangeCodeForToken } from './oauth';
import { errorHandler } from '../middleware/errorHandler';

const router = Router();

/**
 * Initiates the Dropbox OAuth flow.  Errors during state storage are
 * caught and a generic message is returned to the user.
 */
router.get('/auth/dropbox', async (req: Request, res: Response) => {
  try {
    const state = Math.random().toString(36).substring(2);
    await storeOAuthState(state);
    const url = buildAuthUrl(state);
    res.redirect(url);
  } catch (e) {
    logger.error('Failed to initiate Dropbox auth', e);
    res
      .status(500)
      .send('Failed to start Dropbox authentication. Please try again.');
  }
});

/**
 * Handles the OAuth callback.  All raw exception strings and upstream
 * HTTP bodies are suppressed and replaced with a generic error message.
 */
router.get('/auth/dropbox/callback', async (req: Request, res: Response) => {
  try {
    const { code, state } = req.query;
    if (!code || !state) {
      throw new Error('Missing code or state in callback');
    }

    const storedState = await getOAuthState(state as string);
    if (!storedState) {
      throw new Error('Invalid OAuth state');
    }

    const token = await exchangeCodeForToken(code as string);
    // Store token, etc. – omitted for brevity
    res.send('Dropbox authentication successful!');
  } catch (e) {
    logger.error('Dropbox callback error', e);
    res
      .status(400)
      .send('Dropbox authentication failed. Please try again.');
  }
});

export default router;
