import { FastifyInstance } from "fastify";
import * as z from "zod";
import { authID, authUser } from "./auth";
import { getSession, listSessions, startSession, stopSession } from "../../tracking/session";
import { uploadAudioChunk } from "../../tracking/files";
import { sessionToAPI, sessionToFullAPI } from "../convert";

export async function session(app: FastifyInstance) {
    const sessionStartSchema = z.object({
        repeatKey: z.string(),
        timeout: z.number(),
    }).strict();
    app.post('/session/start', async (request, reply) => {
        const body = sessionStartSchema.safeParse(request.body);
        if (!body.success) {
            reply.code(400);
            return { ok: false, error: 'invalid_request' };
        }
        let uid = authUser(request);
        let tid = authID(request);
        let session = await startSession(uid, tid, body.data.repeatKey, body.data.timeout);
        return {
            ok: true,
            session: sessionToAPI(session)
        };
    });
    const sessionStopSchema = z.object({
        session: z.string(),
    }).strict();
    app.post('/session/stop', async (request, reply) => {
        const body = sessionStopSchema.safeParse(request.body);
        if (!body.success) {
            reply.code(400);
            return { ok: false, error: 'invalid_request' };
        }
        let uid = authUser(request);
        let result = await stopSession(uid, body.data.session);
        return {
            ok: result
        };
    });
    const sessionUploadAudioSchema = z.object({
        session: z.string(),
        repeatKey: z.string(),
        format: z.string(),
        chunks: z.array(z.string()),
    }).strict();
    app.post('/session/upload/audio', async (request, reply) => {
        const body = sessionUploadAudioSchema.safeParse(request.body);
        if (!body.success) {
            reply.code(400);
            return { ok: false, error: 'invalid_request' };
        }
        let uid = authUser(request);
        let result = await uploadAudioChunk(
            uid,
            body.data.session,
            body.data.repeatKey,
            body.data.format,
            body.data.chunks.map((chunk) => Buffer.from(chunk, 'base64'))
        );
        return {
            ok: result
        };
    });

    const sessionsList = z.object({
        after: z.string().optional().nullable(),
    }).strict();
    app.post('/session/list', async (request, reply) => {
        const body = sessionsList.safeParse(request.body);
        if (!body.success) {
            reply.code(400);
            return { ok: false, error: 'invalid_request' };
        }
        let uid = authUser(request);
        let res = await listSessions(uid, body.data.after ? body.data.after : null);
        return {
            ok: true,
            sessions: res.sessions.map((v) => sessionToAPI(v)),
            next: res.next
        };
    });
    const sessionRequest = z.object({
        id: z.string()
    }).strict();
    app.post('/session/get', async (request, reply) => {
        const body = sessionRequest.safeParse(request.body);
        if (!body.success) {
            reply.code(400);
            return { ok: false, error: 'invalid_request' };
        }
        let uid = authUser(request);
        let res = await getSession(uid, body.data.id);
        return {
            ok: true,
            session: sessionToFullAPI(res)
        };
    });
}