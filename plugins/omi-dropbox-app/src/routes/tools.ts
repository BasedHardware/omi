import { Request, Response, NextFunction } from 'express';
import { Dropbox } from 'dropbox';
import { logger } from '../utils/logger';

const dbx = new Dropbox({ accessToken: process.env.DROPBOX_ACCESS_TOKEN! });

export const searchFiles = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { query } = req.body;
    const result = await dbx.filesSearchV2({ query });
    res.json(result);
  } catch (e: any) {
    logger.error('Search error', { error: e.message });
    res.status(500).json({ error: 'An error occurred while searching files.' });
  }
};

export const listFolder = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { path } = req.body;
    const result = await dbx.filesListFolder({ path });
    res.json(result);
  } catch (e: any) {
    logger.error('List error', { error: e.message });
    res.status(500).json({ error: 'An error occurred while listing the folder.' });
  }
};

export const readFile = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { path } = req.body;
    const download = await dbx.filesDownload({ path });
    const fileContent = download.result.fileBinary; // Assuming binary buffer
    // If PDF extraction is required, wrap it in a try/catch
    res.send(fileContent);
  } catch (e: any) {
    logger.error('Read error', { error: e.message });
    res.status(500).json({ error: 'An error occurred while reading the file.' });
  }
};
