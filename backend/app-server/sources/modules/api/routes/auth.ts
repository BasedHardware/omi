import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import * as z from "zod";
import { completeAuth, resolveToken, startAuth } from "../../auth/operations";

export async function auth(app: FastifyInstance) {
    const authStartSchema = z.object({
        key: z.string(),
        phone: z.string(),
    }).strict();
    app.post('/start', async (request, reply) => {
        const body = authStartSchema.safeParse(request.body);
        if (!body.success) {
            reply.code(400);
            return { ok: false, error: 'invalid_request' };
        }
        return await startAuth(body.data.phone, body.data.key);
    });

    const authVerifySchema = z.object({
        phone: z.string(),
        code: z.string(),
        key: z.string(),
    }).strict();
    app.post('/verify', async (request, reply) => {
        const body = authVerifySchema.safeParse(request.body);
        if (!body.success) {
            reply.code(400);
            return { ok: false, error: 'invalid_request' };
        }
        return await completeAuth(body.data.phone, body.data.key, body.data.code);
    });
}

export function tokenAuthPlugin(requireUser: boolean) {
    return async function (request: FastifyRequest, reply: FastifyReply) {

        // Check for token
        const authHeader = request.headers.authorization;
        if (!authHeader || !authHeader.startsWith('Bearer ')) {
            reply.status(401).send({ error: 'Unauthorized' });
            return;
        }

        // Load token
        const token = authHeader.split(' ')[1];
        let resolved = await resolveToken(token);
        if (!resolved) {
            reply.status(401).send({ error: 'Invalid token' });
            return;
        }
        if (requireUser && !resolved.user) {
            reply.status(401).send({ error: 'User not found' });
            return;
        }

        // Store auth data
        (request as any).setAuth(resolved.phone, resolved.id, resolved.user ? resolved.user : null);
    };
}

export function authUser(request: FastifyRequest) {
    if (!(request as any).auth.user) {
        throw new Error('No user in request');
    }
    return (request as any).auth.user as string;
}

export function authPhone(request: FastifyRequest) {
    return (request as any).auth.phone as string;
}

export function authID(request: FastifyRequest) {
    return (request as any).auth.id as string;
}