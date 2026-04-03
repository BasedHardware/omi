import { NextRequest, NextResponse } from 'next/server'
import admin, { getDb } from '@/lib/firebase/admin'
import { verifyAdmin } from '@/lib/auth'
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request)
  if (authResult instanceof NextResponse) return authResult

  try {
    const db = getDb();
    const snapshot = await db.collection('distributors').orderBy('createdAt', 'desc').get()

    const distributors = snapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
      createdAt: doc.data().createdAt?.toDate?.()?.toISOString() || null,
      lastLoginAt: doc.data().lastLoginAt?.toDate?.()?.toISOString() || null,
    }))

    return NextResponse.json({ distributors })
  } catch (error) {
    console.error('Error fetching distributors:', error)
    return NextResponse.json({ error: 'Failed to fetch distributors' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request)
  if (authResult instanceof NextResponse) return authResult

  try {
    const db = getDb();
    const body = await request.json()
    const { email, name, isActive, isAdmin, countries, locationId, locationName } = body

    if (!email || !name) {
      return NextResponse.json(
        { error: 'Missing required fields: email, name' },
        { status: 400 }
      )
    }

    // Check for duplicate email
    const existing = await db.collection('distributors').where('email', '==', email).get()
    if (!existing.empty) {
      return NextResponse.json(
        { error: 'A distributor with this email already exists' },
        { status: 409 }
      )
    }

    const now = admin.firestore.Timestamp.now()

    const distributorData = {
      email,
      name,
      avatarUrl: null,
      isActive: isActive ?? true,
      isAdmin: isAdmin ?? false,
      countries: countries || [],
      locationId: locationId || null,
      locationName: locationName || null,
      createdAt: now,
      lastLoginAt: null,
    }

    const docRef = await db.collection('distributors').add(distributorData)

    return NextResponse.json({
      success: true,
      id: docRef.id,
      distributor: {
        id: docRef.id,
        ...distributorData,
        createdAt: now.toDate().toISOString(),
      },
    })
  } catch (error) {
    console.error('Error creating distributor:', error)
    return NextResponse.json({ error: 'Failed to create distributor' }, { status: 500 })
  }
}

export async function PUT(request: NextRequest) {
  const authResult = await verifyAdmin(request)
  if (authResult instanceof NextResponse) return authResult

  try {
    const db = getDb();
    const body = await request.json()
    const { id, ...updates } = body

    if (!id) {
      return NextResponse.json({ error: 'Missing required field: id' }, { status: 400 })
    }

    const docRef = db.collection('distributors').doc(id)
    const doc = await docRef.get()

    if (!doc.exists) {
      return NextResponse.json({ error: 'Distributor not found' }, { status: 404 })
    }

    // Only allow specific fields to be updated
    const allowedFields = ['name', 'isActive', 'isAdmin', 'countries', 'locationId', 'locationName']
    const sanitizedUpdates: Record<string, unknown> = {}
    for (const field of allowedFields) {
      if (updates[field] !== undefined) {
        sanitizedUpdates[field] = updates[field]
      }
    }

    await docRef.update(sanitizedUpdates)

    const updated = await docRef.get()

    return NextResponse.json({
      success: true,
      distributor: {
        id: updated.id,
        ...updated.data(),
        createdAt: updated.data()?.createdAt?.toDate?.()?.toISOString() || null,
        lastLoginAt: updated.data()?.lastLoginAt?.toDate?.()?.toISOString() || null,
      },
    })
  } catch (error) {
    console.error('Error updating distributor:', error)
    return NextResponse.json({ error: 'Failed to update distributor' }, { status: 500 })
  }
}
