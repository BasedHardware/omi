import { Router, Request, Response } from 'express';
import { logger } from '../../utils/logger';
import { synthesizeSpeech } from './audioService';
import { errorHandler } from '../middleware/errorHandler';

const router = Router();

/**
 * Audio endpoint – returns a generic error message on failure.
 */
router.post('/audio', async (req: Request, res: Response) => {
  try {
    const { text } = req.body;
    const audioBuffer = await synthesizeSpeech(text);
    res.set('Content-Type', 'audio/mpeg');
    res.send(audioBuffer);
  } catch (e) {
    logger.error('Audio synthesis error', e);
    res.status(500).json({ message: 'Audio generation failed. Please try again.' });
  }
});

export default router;
