import { NextRequest, NextResponse } from 'next/server';
import envConfig from '@/src/constants/envConfig';

const API_URL = process.env.API_URL || 'https://nooto.togodynamics.com';

export async function GET(request: NextRequest) {
  const adminKey = request.headers.get('x-admin-key');

  if (!adminKey) {
    return NextResponse.json(
      { error: 'Admin key required' },
      { status: 401 }
    );
  }

  try {
    const response = await fetch(`${API_URL}/v1/apps/public/unapproved`, {
      headers: {
        'secret-key': adminKey,
      },
    });

    if (!response.ok) {
      const error = await response.text();
      return NextResponse.json(
        { error: error || 'Failed to fetch apps' },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error fetching unapproved apps:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
