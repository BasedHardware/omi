import { Router, Request, Response } from 'express';
import { logger } from '../../utils/logger';
import { searchFiles, listFolder, readFile } from './dropboxClient';
import { errorHandler } from '../middleware/errorHandler';

const router = Router();

/**
 * Search tool – returns a sanitized error message on failure.
 */
router.post('/tools/search', async (req: Request, res: Response) => {
  try {
    const { query } = req.body;
    const results = await searchFiles(query);
    res.json({ results });
  } catch (e) {
    logger.error('Search error', e);
    res.status(500).json({ error: 'Search failed. Please try again later.' });
  }
});

/**
 * List tool – returns a sanitized error message on failure.
 */
router.post('/tools/list', async (req: Request, res: Response) => {
  try {
    const { path } = req.body;
    const entries = await listFolder(path);
    res.json({ entries });
  } catch (e) {
    logger.error('List error', e);
    res.status(500).json({ error: 'Listing failed. Please try again later.' });
  }
});

/**
 * Read tool – returns a sanitized error message on failure.
 */
router.post('/tools/read', async (req: Request, res: Response) => {
  try {
    const { path } = req.body;
    const content = await readFile(path);
    res.json({ content });
  } catch (e) {
    logger.error('Read error', e);
    res.status(500).json({ error: 'Read failed. Please try again later.' });
  }
});

export default router;
