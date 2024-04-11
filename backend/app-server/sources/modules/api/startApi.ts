import fastify from "fastify";
import { log } from "../../utils/log";
import { auth, tokenAuthPlugin } from "./routes/auth";
import { pre } from "./routes/pre";
import { session } from "./routes/session";
import { updates } from "./routes/updates";

export async function startApi() {

    // Configure
    log('Starting API...');

    // Start API
    const app = fastify({
        logger: true,
        trustProxy: true,
    });
    app.register(require('@fastify/cors'), {
        origin: '*',
        allowedHeaders: '*',
        methods: ['GET', 'POST']
    });
    app.decorateRequest('setAuth', function (phone: string, id: string, user: string | null) {
        (this as any).auth = { phone, user, id };
    })
    app.get('/', function (request, reply) {
        reply.send('Welcome to Super!');
    });

    // Auth routes
    app.register(auth, { prefix: '/auth' });

    // Onboarding routes
    app.register(async (sub) => {
        sub.addHook('preHandler', tokenAuthPlugin(false));
        pre(sub);
    }, { prefix: '/pre' });

    // Authenticated routes
    app.register(async function (sub) {
        sub.addHook('preHandler', tokenAuthPlugin(true));
        session(sub);
        updates(sub);
    }, { prefix: '/app' });

    // Start
    const port = process.env.PORT ? parseInt(process.env.PORT, 10) : 3001;
    await app.listen({ port, host: '0.0.0.0' });

    // End
    log('API ready on port http://localhost:' + port);
}