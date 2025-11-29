import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.API_URL || 'https://nooto.togodynamics.com';

export async function POST(
  request: NextRequest,
  { params }: { params: { appId: string } }
) {
  const adminKey = request.headers.get('x-admin-key');
  const { searchParams } = new URL(request.url);
  const uid = searchParams.get('uid');

  if (!adminKey) {
    return NextResponse.json({ error: 'Admin key required' }, { status: 401 });
  }

  if (!uid) {
    return NextResponse.json({ error: 'User ID required' }, { status: 400 });
  }

  try {
    const response = await fetch(
      `${API_URL}/v1/apps/${params.appId}/approve?uid=${uid}`,
      {
        method: 'POST',
        headers: {
          'secret-key': adminKey,
        },
      }
    );

    if (!response.ok) {
      const error = await response.text();
      return NextResponse.json(
        { error: error || 'Failed to approve app' },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error approving app:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
