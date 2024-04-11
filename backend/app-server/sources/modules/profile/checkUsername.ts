const reservedNames = new Set([
    'signup',
    'root',
    'init',
    'invite',
    'channel',
    'joinChannel',
    'need_info',
    'activation',
    'waitlist',
    'suspended',
    'createProfile',
    'createOrganization',
    'join',
    '404',
    'acceptChannelInvite',
    'map',
    'settings',
    'profile',
    'notifications',
    'invites',
    'dev',
    'organization',
    'new',
    'feed',
    'directory',
    'main',
    'people',
    'organizations',
    'communities',
    'marketplace',
    'mail',
    'super',
    'compatibility',
    'performance',
    'landing',
    'auth',
    'login',
    'logout',
    'complete',
    'privacy',
    'terms',
    'about',
    'users'
]);

export function checkUsername(src: string) {
    if (src.length < 5) {
        return false;
    }
    if (src.length > 16) {
        return false;
    }
    if (!/^\w*$/.test(src)) {
        return false;
    }
    let normalized = src.toLowerCase();
    if (reservedNames.has(normalized)) {
        return false;
    }
    return true;
}