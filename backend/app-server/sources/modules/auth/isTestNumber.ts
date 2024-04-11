import parsePhoneNumber from 'libphonenumber-js';

export function isTestNumber(number: string): boolean {
    let parsed = parsePhoneNumber(number);
    if (!parsed) {
        return false;
    }
    if (parsed.countryCallingCode === '1') {
        return parsed.nationalNumber.startsWith('555') && parsed.nationalNumber.length === 10;
    }
    return false;
}