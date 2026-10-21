import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { verifyAdmin } from "@/lib/auth";
import { getAdminAuth, getDb } from "@/lib/firebase/admin";
import { sendAdminInviteEmail } from "@/lib/email/invite";

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

function errorCode(error: unknown): string | undefined {
  if (error && typeof error === "object" && "code" in error) {
    const code = (error as { code: unknown }).code;
    if (typeof code === "string") return code;
  }
  return undefined;
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
    let provisioned = false;
    try {
      firebaseUser = await getAdminAuth().getUserByEmail(email);
    } catch (error) {
      if (errorCode(error) !== "auth/user-not-found") throw error;
      // The invitee has never signed in to Omi, so no Firebase Auth user
      // exists to key `adminData/{uid}` on. Reserve the uid now with an
      // unverified, credential-less account: the project keeps Firebase's
      // default one-account-per-email setting, so when they later sign in
      // with Google for this address the provider links into this very uid
      // and the admin grant below is already waiting for them.
      try {
        firebaseUser = await getAdminAuth().createUser({
          email,
          emailVerified: false,
        });
        provisioned = true;
      } catch (createError) {
        // Lost a race with a concurrent add (or with their first sign-in).
        if (errorCode(createError) !== "auth/email-already-exists") {
          throw createError;
        }
        firebaseUser = await getAdminAuth().getUserByEmail(email);
      }
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

    // The grant has landed. Telling them about it is best effort: a mail
    // failure is reported in the response, never rolled back into an error.
    let invitedBy: string | null = null;
    try {
      const inviterDoc = await db
        .collection("adminData")
        .doc(authResult.uid)
        .get();
      const inviterEmail = inviterDoc.data()?.email;
      invitedBy = typeof inviterEmail === "string" ? inviterEmail : null;
    } catch (error) {
      console.error("Could not read the inviting admin's email:", error);
    }

    const invite = await sendAdminInviteEmail({ email, invitedBy });
    if (!invite.sent) {
      console.error(
        `Admin invite email not sent to ${email} (reason ${
          invite.reason ?? "unknown"
        })`
      );
    }

    return NextResponse.json(
      { teamMember, provisioned, emailSent: invite.sent },
      { status: 201 }
    );
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
