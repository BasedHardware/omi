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

const removeTeamMemberSchema = z.object({
  uid: z.string().trim().min(1),
});

/**
 * The workspace owner is an admin whose `adminData/{uid}` doc carries
 * `owner: true`. Only the owner can remove other admins, including
 * superadmins. Ownership is data, not a role string, so a superadmin cannot
 * grant it to themselves through the "Add new person" flow.
 */
function isOwnerDoc(data: FirebaseFirestore.DocumentData | undefined) {
  return data?.owner === true;
}

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
        owner: isOwnerDoc(data),
      };
    });

    const viewerDoc = snapshot.docs.find((doc) => doc.id === authResult.uid);

    return NextResponse.json({
      teamMembers: members,
      viewer: {
        uid: authResult.uid,
        canRemove: isOwnerDoc(viewerDoc?.data()),
      },
    });
  } catch (error) {
    console.error("Error fetching team members:", error);
    return NextResponse.json(
      { error: "Failed to fetch team members" },
      { status: 500 }
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
      { status: 400 }
    );
  }

  const parsedBody = addTeamMemberSchema.safeParse(body);
  if (!parsedBody.success) {
    return NextResponse.json(
      { error: "A valid email is required" },
      { status: 400 }
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
          { status: 404 }
        );
      }
      throw error;
    }

    const db = getDb();
    const memberRef = db.collection("adminData").doc(firebaseUser.uid);
    if ((await memberRef.get()).exists) {
      return NextResponse.json(
        { error: `${email} already has admin access.` },
        { status: 409 }
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
      { status: 500 }
    );
  }
}

export async function DELETE(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "A member uid is required" },
      { status: 400 }
    );
  }

  const parsedBody = removeTeamMemberSchema.safeParse(body);
  if (!parsedBody.success) {
    return NextResponse.json(
      { error: "A member uid is required" },
      { status: 400 }
    );
  }

  const { uid } = parsedBody.data;

  try {
    const db = getDb();
    const collection = db.collection("adminData");

    const callerDoc = await collection.doc(authResult.uid).get();
    if (!isOwnerDoc(callerDoc.data())) {
      return NextResponse.json(
        { error: "Only the workspace owner can remove admins." },
        { status: 403 }
      );
    }

    if (uid === authResult.uid) {
      return NextResponse.json(
        { error: "You cannot remove yourself." },
        { status: 400 }
      );
    }

    const memberRef = collection.doc(uid);
    const memberDoc = await memberRef.get();
    if (!memberDoc.exists) {
      return NextResponse.json(
        { error: "That person no longer has admin access." },
        { status: 404 }
      );
    }

    const data = memberDoc.data() ?? {};
    await memberRef.delete();
    console.log(
      `Admin ${authResult.uid} removed admin ${uid} (${
        data.email ?? "no email"
      }, role ${data.role ?? "Admin"})`
    );

    return NextResponse.json({
      removed: {
        id: uid,
        email: data.email ?? null,
        role: data.role ?? "Admin",
      },
    });
  } catch (error) {
    console.error("Error removing team member:", error);
    return NextResponse.json(
      { error: "Failed to remove team member" },
      { status: 500 }
    );
  }
}
