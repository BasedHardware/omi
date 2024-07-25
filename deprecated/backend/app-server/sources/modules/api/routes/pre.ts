import { FastifyInstance } from "fastify";
import * as z from "zod";
import { authPhone } from "./auth";
import { completeProfile, resolvePreState, saveName, saveUsername } from "../../profile/pre";

export async function pre(app: FastifyInstance) {
    app.get('/state', async (request, reply) => {
        let phone = authPhone(request);
        return await resolvePreState(phone);
    });
    const usernameCreateSchema = z.object({
        username: z.string(),
    }).strict();
    app.post('/username', async (request, reply) => {
        const body = usernameCreateSchema.safeParse(request.body);
        if (!body.success) {
            reply.code(400);
            return { ok: false, error: 'invalid_request' };
        }
        let phone = authPhone(request);
        let res = await saveUsername(phone, body.data.username.trim());
        if (res !== 'ok') {
            return { ok: false, error: res };
        } else {
            return { ok: true };
        }
    });
    const nameCreateSchema = z.object({
        firstName: z.string(),
        lastName: z.string().nullable().optional(),
    }).strict();
    app.post('/name', async (request, reply) => {
        const body = nameCreateSchema.safeParse(request.body);
        if (!body.success) {
            reply.code(400);
            return { ok: false, error: 'invalid_request' };
        }
        let phone = authPhone(request);
        let firstName = body.data.firstName.trim();
        let lastName: string | null = body.data.lastName?.trim() ?? null;
        if (lastName === '') {
            lastName = null;
        }
        let res = await saveName(phone, firstName, lastName);
        if (res !== 'ok') {
            return { ok: false, error: res };
        } else {
            return { ok: true };
        }
    });
    app.post('/complete', async (request, reply) => {
        let phone = authPhone(request);
        let res = await completeProfile(phone);
        if (res !== 'ok') {
            return { ok: false, error: res };
        } else {
            return { ok: true };
        }
    });
}