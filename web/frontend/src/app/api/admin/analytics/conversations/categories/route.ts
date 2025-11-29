import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.API_URL || 'http://localhost:8000';

export async function GET(request: NextRequest) {
  const adminKey = request.headers.get('x-admin-key');

  if (!adminKey) {
    return NextResponse.json({ error: 'Admin key required' }, { status: 401 });
  }

  try {
    const response = await fetch(`${API_URL}/v1/admin/analytics/conversations/categories`, {
      method: 'GET',
      headers: {
        'secret-key': adminKey,
      },
      cache: 'no-store',
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: 'Failed to fetch conversation categories' },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error fetching conversation categories:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
