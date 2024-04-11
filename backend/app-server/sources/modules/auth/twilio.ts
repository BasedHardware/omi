import tw from 'twilio';

export const twilio = tw(
    process.env.TWILIO_ACCOUNT_SID,
    process.env.TWILIO_AUTH_TOKEN
);

export async function validateNumber(src: string): Promise<boolean> {
    try {
        let result = await twilio.lookups.v2.phoneNumbers(src).fetch();
        return result.valid;
    } catch (e) {
        console.warn(e);
        return false;
    }
}

export async function sendSms(number: string, body: string) {
    return (await twilio.messages.create({
        from: process.env.TWILIO_NUMBER,
        to: number,
        body: body
    })).sid;
}

export async function redactSms(sid: string) {
    await twilio.messages(sid).update({
        body: ''
    });
}

