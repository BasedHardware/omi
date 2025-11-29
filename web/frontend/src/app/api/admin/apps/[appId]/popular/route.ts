import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.API_URL || 'https://nooto.togodynamics.com';

export async function PATCH(
  request: NextRequest,
  { params }: { params: { appId: string } }
) {
  const adminKey = request.headers.get('x-admin-key');
  const { searchParams } = new URL(request.url);
  const value = searchParams.get('value');

  if (!adminKey) {
    return NextResponse.json({ error: 'Admin key required' }, { status: 401 });
  }

  if (value === null) {
    return NextResponse.json({ error: 'Value parameter required' }, { status: 400 });
  }

  try {
    const response = await fetch(
      `${API_URL}/v1/apps/${params.appId}/popular?value=${value}`,
      {
        method: 'PATCH',
        headers: {
          'secret-key': adminKey,
        },
      }
    );

    if (!response.ok) {
      const error = await response.text();
      return NextResponse.json(
        { error: error || 'Failed to update app popularity' },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error updating app popularity:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
