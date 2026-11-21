"""Shared exact-UID route and contact contract for the isolated Redis pilot."""

import re
from urllib.parse import unquote, urlsplit

REDIS_PAGER_UID = 'omi-redis-cache-conn-page'
REDIS_PAGER_TARGET = 'prod-serving-redis'
REDIS_PAGER_RECEIVER = 'Omi - Redis phone wake'
REDIS_CONTACT_UID = 'omi-redis-phone-wake'
TELEGRAM_RECEIVER = 'Omi - Services Alerting (Telegram)'
PUBLISHER_PATH = '/v1/publish/grafana-redis'
CONTACT_POINTS_PATH = '/api/v1/provisioning/contact-points'
POLICIES_PATH = '/api/v1/provisioning/policies'


def rule_route_error(uid: str, rule: dict) -> str | None:
    labels = rule.get('labels')
    if not isinstance(labels, dict) or labels.get('alert_identity') != uid or rule.get('uid') != uid:
        return f'{uid}: invalid alert_identity or UID'
    pilot = uid == REDIS_PAGER_UID
    expected = REDIS_PAGER_RECEIVER if pilot else TELEGRAM_RECEIVER
    settings = rule.get('notification_settings')
    if not isinstance(settings, dict) or settings.get('receiver') != expected:
        return f'{uid}: unexpected notification receiver (expected {expected})'
    if pilot and labels.get('paging_target') != REDIS_PAGER_TARGET:
        return f'{uid}: invalid paging_target (expected {REDIS_PAGER_TARGET})'
    return None


def validate_publisher_url(url: str) -> None:
    if not re.fullmatch(r'https://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app' + PUBLISHER_PATH, url):
        raise ValueError('Redis pilot requires the reviewed HTTPS Cloud Run relay publisher URL')


def _uses_publisher(settings: object, publisher_hosts: set[str | None]) -> bool:
    if not isinstance(settings, dict) or not isinstance(settings.get('url'), str):
        return False
    try:
        parsed = urlsplit(settings['url'])
        host = parsed.hostname
        return (
            host is not None
            and host.rstrip('.') in publisher_hosts
            and unquote(parsed.path).rstrip('/') == PUBLISHER_PATH
        )
    except ValueError:
        return False


def redis_contact_error(contacts: object, publisher_url: str, alias_hosts: tuple[str, ...] = ()) -> str | None:
    validate_publisher_url(publisher_url)
    if any(not re.fullmatch(r'[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+\.?', host) for host in alias_hosts):
        raise ValueError('Redis pilot aliases must be reviewed DNS hostnames')
    integrations = contacts if isinstance(contacts, list) else []
    points = [point for point in integrations if isinstance(point, dict) and point.get('name') == REDIS_PAGER_RECEIVER]
    # Every integration with the contact name receives the alert. A single
    # matching webhook is insufficient if a second integration fans it out.
    if (
        len(points) != 1
        or points[0].get('uid') != REDIS_CONTACT_UID
        or points[0].get('type') != 'webhook'
        or points[0].get('disableResolveMessage') is not False
    ):
        return 'Redis pilot requires exactly one webhook integration with resolved notifications enabled'
    settings = points[0].get('settings')
    if (
        not isinstance(settings, dict)
        or settings.get('url') != publisher_url
        or settings.get('httpMethod', 'POST') != 'POST'
    ):
        return 'Redis pilot webhook does not match the reviewed publisher URL and POST method'
    if settings.get('payload') not in (None, {}):
        return 'Redis pilot webhook must use the default Grafana alert payload'
    tls = settings.get('tlsConfig', {})
    if not isinstance(tls, dict) or tls.get('insecureSkipVerify', False) is not False:
        return 'Redis pilot webhook must verify the relay TLS certificate'
    hmac = settings.get('hmacConfig')
    if (
        not isinstance(hmac, dict)
        or hmac.get('header') != 'X-Grafana-Alerting-Signature'
        or hmac.get('timestampHeader') != 'X-Grafana-Alerting-Timestamp'
        or '[REDACTED]' not in (hmac.get('secret'), settings.get('hmacConfig.secret'))
    ):
        return 'Redis pilot webhook is missing verified timestamped HMAC settings'
    publisher_hosts = {urlsplit(publisher_url).hostname, *(host.lower().rstrip('.') for host in alias_hosts)}
    if any(
        isinstance(point, dict) and point is not points[0] and _uses_publisher(point.get('settings'), publisher_hosts)
        for point in integrations
    ):
        return 'Redis pilot publisher URL is shared by another contact point'
    return None


def redis_receiver_scope_error(rules: dict[str, dict], root_policy: object) -> str | None:
    for uid, rule in rules.items():
        settings = rule.get('notification_settings')
        if uid != REDIS_PAGER_UID and isinstance(settings, dict) and settings.get('receiver') == REDIS_PAGER_RECEIVER:
            return 'Redis pilot receiver is assigned to another Grafana rule'
    policies = [root_policy]
    while policies:
        policy = policies.pop()
        if not isinstance(policy, dict):
            return 'Grafana notification policy readback is invalid'
        if policy.get('receiver') == REDIS_PAGER_RECEIVER:
            return 'Redis pilot receiver is assigned to a Grafana notification policy'
        children = policy.get('routes', [])
        if not isinstance(children, list):
            return 'Grafana notification policy routes are invalid'
        policies.extend(children)
    return None
