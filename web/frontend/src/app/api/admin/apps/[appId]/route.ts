import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.API_URL || 'https://nooto.togodynamics.com';

export async function PATCH(
  request: NextRequest,
  { params }: { params: { appId: string } }
) {
  const adminKey = request.headers.get('x-admin-key');

  if (!adminKey) {
    return NextResponse.json({ error: 'Admin key required' }, { status: 401 });
  }

  try {
    // Get the form data from the request
    const formData = await request.formData();

    // Forward the form data to the backend
    const response = await fetch(
      `${API_URL}/v1/admin/apps/${params.appId}`,
      {
        method: 'PATCH',
        headers: {
          'secret-key': adminKey,
        },
        body: formData,
      }
    );

    if (!response.ok) {
      const error = await response.text();
      return NextResponse.json(
        { error: error || 'Failed to update app' },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error updating app:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
