import express from 'express';
import authRouter from './routes/auth';
import toolsRouter from './routes/tools';
import audioRouter from './routes/audio';
import { errorHandler } from './middleware/errorHandler';
import { sanitizeResponse } from './middleware/sanitizeResponse';

const app = express();

app.use(express.json());
app.use(sanitizeResponse);

app.use(authRouter);
app.use(toolsRouter);
app.use(audioRouter);

// Global error handler – must be the last middleware
app.use(errorHandler);

export default app;
