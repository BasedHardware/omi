import robots from '../robots';

export function GET(): Response {
  const policy = robots();
  const lines = policy.rules.flatMap((rule) => [
    `User-agent: ${rule.userAgent}`,
    `Allow: ${rule.allow}`,
    ...rule.disallow.map((path) => `Disallow: ${path}`),
  ]);
  lines.push(`Sitemap: ${policy.sitemap}`);
  return new Response(`${lines.join('\n')}\n`, {
    headers: { 'content-type': 'text/plain; charset=utf-8' },
  });
}
