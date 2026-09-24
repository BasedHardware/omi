import { Request, Response, NextFunction } from 'express';
import { Dropbox } from 'dropbox';
import { getOAuthState, setOAuthState } from '../services/state';
import { logger } from '../utils/logger';

export const authDropbox = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const state = req.query.state as string;
    if (!state) {
      return res.status(400).send('Missing state parameter');
    }
    await setOAuthState(state, req.session.id);
    const dbx = new Dropbox({ clientId: process.env.DROPBOX_CLIENT_ID! });
    const authUrl = dbx.getAuthenticationUrl(process.env.DROPBOX_REDIRECT_URI!, state);
    res.redirect(authUrl);
  } catch (e: any) {
    logger.error('Error initiating Dropbox OAuth', { error: e.message });
    res.status(500).send('An unexpected error occurred while starting Dropbox authentication.');
  }
};

export const authDropboxCallback = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { code, state } = req.query as { code: string; state: string };
    if (!code || !state) {
      return res.status(400).send('Missing code or state in callback');
    }

    const storedState = await getOAuthState(req.session.id);
    if (state !== storedState) {
      return res.status(400).send('Invalid state parameter');
    }

    const dbx = new Dropbox({ clientId: process.env.DROPBOX_CLIENT_ID!, clientSecret: process.env.DROPBOX_CLIENT_SECRET! });
    const tokenResponse = await dbx.getAccessTokenFromCode(process.env.DROPBOX_REDIRECT_URI!, code as string);
    // Persist token securely here (omitted for brevity)
    res.send('Dropbox authentication successful. You may close this window.');
  } catch (e: any) {
    logger.error('Dropbox OAuth callback error', { error: e.message });
    // Render a minimal error page without leaking details
    res.status(500).send(`
      <html>
        <body>
          <h1>Authentication Error</h1>
          <p>We encountered an error while processing your Dropbox authentication. Please try again.</p>
        </body>
      </html>
    `);
  }
};
