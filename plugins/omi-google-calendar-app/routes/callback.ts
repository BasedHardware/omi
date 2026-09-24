import { Router, Request, Response } from 'express';
import { logger } from '../utils/logger';
import { handleAuthCallback } from '../services/callback';

const router = Router();

router.get('/auth/google/callback', async (req: Request, res: Response) => {
  try {
    await handleAuthCallback(req);
    res.sendFile(process.env.DARK_ERROR_CARD_PATH ?? 'public/error.html');
  } catch (e) {
    logger.error('Authentication error during callback', {
      error: e instanceof Error ? e.message : String(e),
    });
    // Render a safe dark‑themed error card
    res.status(500).sendFile(process.env.DARK_ERROR_CARD_PATH ?? 'public/error.html');
  }
});

export default router;
