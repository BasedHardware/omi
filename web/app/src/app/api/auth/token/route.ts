import { moonshineJson } from '@tschk/moonshine-next/server';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';
const AUTH_FIELDS = [
  'grant_type',
  'code',
  'redirect_uri',
  'use_custom_token',
  'code_verifier',
] as const;

export async function POST(request: Request) {
  const form = await request.formData();
  const body = new URLSearchParams();
  for (const field of AUTH_FIELDS) {
    const value = form.get(field);
    if (typeof value !== 'string' || !value) {
      return moonshineJson({ detail: `${field} is required` }, { status: 400 });
    }
    body.set(field, value);
  }

  const response = await fetch(`${API_BASE_URL}/v1/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  const contentType = response.headers.get('content-type') || 'application/json';
  return new Response(response.body, {
    status: response.status,
    headers: { 'Content-Type': contentType },
  });
}
