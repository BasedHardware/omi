import { AsyncLock } from "teslabot";
import { normalizePhone } from "../../utils/normalize";
import { twilio, validateNumber } from "./twilio";
import { inTx } from "../storage/inTx";
import { generateSafeToken } from "../crypto/generateSafeToken";
import { db } from "../storage/storage";
import { isTestNumber } from "./isTestNumber";

const lock = new AsyncLock();
export type AuthStartResponse = { ok: true, phone: string } | { ok: false, error: 'invalid_number' | 'too_many_attempts' };
export async function startAuth(phone: string, key: string): Promise<AuthStartResponse> {
    return await lock.inLock(async () => {

        // Normalized
        const normalizedPhone = normalizePhone(phone);
        if (!normalizedPhone) {
            return { ok: false, error: 'invalid_number' };
        }

        // Check if this is a test number
        if (isTestNumber(normalizedPhone)) {
            return { ok: true, phone: normalizedPhone };
        }

        // Verify via Twilio
        const isValid = await validateNumber(normalizedPhone);
        if (!isValid) {
            return { ok: false, error: 'invalid_number' };
        }

        // Request verification code
        const output = await twilio.verify.v2.services(process.env.TWILIO_SERVICE_VERIFY!)
            .verifications
            .create({ to: normalizedPhone, channel: 'sms' });
        if (output.status !== 'pending') {
            return { ok: false, error: 'too_many_attempts' };
        }

        return { ok: true, phone: normalizedPhone };
    });
}

export type AuthCompleteResponse = { ok: true, token: string } | { ok: false, error: 'invalid_number' | 'invalid_code' | 'expired_code' };
export async function completeAuth(phone: string, key: string, code: string): Promise<AuthCompleteResponse> {
    return await lock.inLock(async () => {

        // Normalized
        const normalizedPhone = normalizePhone(phone);
        if (!normalizedPhone) {
            return { ok: false, error: 'invalid_number' };
        }

        // Check if this is a test number
        if (isTestNumber(normalizedPhone)) {
            if (code !== normalizedPhone.slice(normalizedPhone.length - 6)) {
                return { ok: false, error: 'invalid_code' };
            }
        } else {
            const output = await twilio.verify.v2.services(process.env.TWILIO_SERVICE_VERIFY!)
                .verificationChecks
                .create({ to: normalizedPhone, code: code });
            if (output.status === 'pending') {
                return { ok: false, error: 'invalid_code' };
            }
            if (output.status === 'canceled') {
                return { ok: false, error: 'expired_code' };
            }
        }

        // Generate token
        const token = await generateSafeToken();

        // Persist token
        await inTx(async (tx) => {

            // Check if token exists
            let ex = await tx.sessionToken.findUnique({ where: { key: token } });
            if (ex) {
                return;
            }

            // Try to find user
            let user = await tx.user.findUnique({ where: { phone: normalizedPhone } });

            // Create token
            await tx.sessionToken.create({ data: { key: token, phone: normalizedPhone, userId: user ? user.id : null } });
        });

        // Return result
        return { ok: true, token };
    });
}

export type ResolveTokenResult = { user?: string, id: string, phone: string } | null;
export async function resolveToken(token: string): Promise<ResolveTokenResult> {

    // Load session
    let session = await db.sessionToken.findUnique({ where: { key: token } });
    if (!session) {
        return null;
    }
    if (session.userId) {
        return { phone: session.phone, id: session.id, user: session.userId };
    } else {
        return { phone: session.phone, id: session.id, };
    }
}