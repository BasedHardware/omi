import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { requireScope } from "@/lib/auth";
import { ROLE_IDS, SCOPES, hasScope } from "@/lib/admin-access";
import {
  addMember,
  listRoster,
  removeMember,
  setMemberRole,
} from "@/lib/team/roster";
import { actorFrom, readJson, teamErrorResponse } from "@/lib/team/http";

export const dynamic = "force-dynamic";

const scopeList = z.array(z.enum(SCOPES)).optional();
const scopeOverrides = z
  .object({ grant: scopeList, deny: scopeList })
  .strict()
  .optional();

const addTeamMemberSchema = z.object({
  email: z
    .string()
    .trim()
    .email()
    .transform((email) => email.toLowerCase()),
  // Least privilege when an older client omits the role.
  accessRole: z.enum(ROLE_IDS).default("viewer"),
  scopeOverrides,
});

const changeRoleSchema = z.object({
  uid: z.string().trim().min(1),
  accessRole: z.enum(ROLE_IDS),
  scopeOverrides,
});

const removeTeamMemberSchema = z.object({
  uid: z.string().trim().min(1),
});

/**
 * Owners are the admins whose `adminData/{uid}` docs carry `owner: true`
 * (there may be more than one); it is set in Firestore, never through this
 * API. Owners and deputies (team:manage) change roles and remove people; only
 * an owner appoints, changes or removes deputies. Nobody changes or removes
 * themselves, and no owner can be changed or removed by anyone — including
 * another owner.
 */
export async function GET(request: NextRequest) {
  const authResult = await requireScope(request, "team:read");
  if (authResult instanceof NextResponse) return authResult;

  try {
    const teamMembers = await listRoster();
    const canManage = hasScope(authResult.access, "team:manage");
    return authResult.json({
      teamMembers,
      viewer: {
        uid: authResult.uid,
        isOwner: authResult.access.kind === "owner",
        canManage,
        canInvite: hasScope(authResult.access, "team:invite"),
        canRemove: canManage,
        scopes: authResult.access.scopes,
      },
    });
  } catch (error) {
    return teamErrorResponse(error, "Failed to fetch team members");
  }
}

export async function POST(request: NextRequest) {
  const authResult = await requireScope(request, "team:invite");
  if (authResult instanceof NextResponse) return authResult;

  const parsedBody = addTeamMemberSchema.safeParse(await readJson(request));
  if (!parsedBody.success) {
    return authResult.json(
      { error: "A valid email is required" },
      { status: 400 }
    );
  }

  try {
    const result = await addMember(actorFrom(authResult), parsedBody.data);
    return authResult.json(result, { status: 201 });
  } catch (error) {
    return teamErrorResponse(error, "Failed to add team member");
  }
}

export async function PATCH(request: NextRequest) {
  const authResult = await requireScope(request, "team:manage");
  if (authResult instanceof NextResponse) return authResult;

  const parsedBody = changeRoleSchema.safeParse(await readJson(request));
  if (!parsedBody.success) {
    return authResult.json(
      { error: "A member uid and a known role are required" },
      { status: 400 }
    );
  }

  const { uid, accessRole, scopeOverrides } = parsedBody.data;
  try {
    const member = await setMemberRole(
      actorFrom(authResult),
      uid,
      accessRole,
      scopeOverrides ?? {}
    );
    return authResult.json({ member });
  } catch (error) {
    return teamErrorResponse(error, "Failed to change role");
  }
}

export async function DELETE(request: NextRequest) {
  const authResult = await requireScope(request, "team:manage");
  if (authResult instanceof NextResponse) return authResult;

  const parsedBody = removeTeamMemberSchema.safeParse(await readJson(request));
  if (!parsedBody.success) {
    return authResult.json(
      { error: "A member uid is required" },
      { status: 400 }
    );
  }

  try {
    const removed = await removeMember(
      actorFrom(authResult),
      parsedBody.data.uid
    );
    return authResult.json({ removed });
  } catch (error) {
    return teamErrorResponse(error, "Failed to remove team member");
  }
}
