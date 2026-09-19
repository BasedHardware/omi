import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { JsonLd, serializeJsonLd } from '@/components/seo/JsonLd';

const PAYLOAD = 'x</script><script>window.__pwned = true</script>';

describe('serializeJsonLd', () => {
  it('escapes < so the JSON cannot close the script element', () => {
    const out = serializeJsonLd({ name: PAYLOAD });
    expect(out).not.toContain('</script>');
    expect(out).toContain('\\u003c/script>');
  });

  it('round-trips: escaped output parses to the original value', () => {
    const data = { name: PAYLOAD, nested: { description: '<b>&amp;</b>' } };
    expect(JSON.parse(serializeJsonLd(data))).toEqual(data);
  });
});

describe('JsonLd', () => {
  it('emits a single script element when app metadata contains </script>', () => {
    const { container } = render(
      <JsonLd data={{ '@type': 'SoftwareApplication', name: PAYLOAD }} />,
    );

    // If the payload were emitted raw, the inner </script> would terminate the
    // JSON-LD element and the attacker's <script> would parse as a sibling.
    const scripts = container.querySelectorAll('script');
    expect(scripts).toHaveLength(1);
    expect(scripts[0].innerHTML).not.toContain('</script>');
    expect(JSON.parse(scripts[0].textContent ?? '').name).toBe(PAYLOAD);
  });
});
