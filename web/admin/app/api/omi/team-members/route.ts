import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { verifyAdmin } from "@/lib/auth";
import { getAdminAuth, getDb } from "@/lib/firebase/admin";

export const dynamic = "force-dynamic";

const addTeamMemberSchema = z.object({
  email: z
    .string()
    .trim()
    .email()
    .transform((email) => email.toLowerCase()),
});

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const db = getDb();
    const snapshot = await db.collection("adminData").get();

    const members = snapshot.docs.map((doc) => {
      const data = doc.data();
      return {
        id: doc.id,
        name: data.name || "Unknown",
        role: data.role || "Admin",
        email: data.email || "No email",
        createdAt: data.createdAt || null,
      };
    });

    return NextResponse.json({ teamMembers: members });
  } catch (error) {
    console.error("Error fetching team members:", error);
    return NextResponse.json(
      { error: "Failed to fetch team members" },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "A valid email is required" },
      { status: 400 },
    );
  }

  const parsedBody = addTeamMemberSchema.safeParse(body);
  if (!parsedBody.success) {
    return NextResponse.json(
      { error: "A valid email is required" },
      { status: 400 },
    );
  }

  const { email } = parsedBody.data;

  try {
    let firebaseUser;
    try {
      firebaseUser = await getAdminAuth().getUserByEmail(email);
    } catch (error) {
      const code =
        error && typeof error === "object" && "code" in error
          ? error.code
          : undefined;
      if (code === "auth/user-not-found") {
        return NextResponse.json(
          {
            error: `No Omi account found for ${email}. Ask them to sign in to Omi once, then try again.`,
          },
          { status: 404 },
        );
      }
      throw error;
    }

    const db = getDb();
    const memberRef = db.collection("adminData").doc(firebaseUser.uid);
    if ((await memberRef.get()).exists) {
      return NextResponse.json(
        { error: `${email} already has admin access.` },
        { status: 409 },
      );
    }

    const teamMember = {
      id: firebaseUser.uid,
      name: firebaseUser.displayName || email,
      role: "Admin",
      email,
    };

    await memberRef.set({
      name: teamMember.name,
      role: teamMember.role,
      email: teamMember.email,
      createdAt: new Date().toISOString(),
    });

    return NextResponse.json({ teamMember }, { status: 201 });
  } catch (error) {
    console.error("Error adding team member:", error);
    return NextResponse.json(
      { error: "Failed to add team member" },
      { status: 500 },
    );
  }
}
