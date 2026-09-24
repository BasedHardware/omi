import { Router, Request, Response } from 'express';
import { logger } from '../utils/logger';
import { startAuthFlow } from '../services/auth';

const router = Router();

router.get('/auth/google', async (_req: Request, res: Response) => {
  try {
    const redirectUrl = await startAuthFlow();
    res.redirect(redirectUrl);
  } catch (e) {
    logger.error('Error initiating Google auth flow', {
      error: e instanceof Error ? e.message : String(e),
    });
    res.status(500).send('An unexpected error occurred while starting authentication.');
  }
});

export default router;
