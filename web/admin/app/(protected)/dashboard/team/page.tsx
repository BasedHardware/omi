"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { AddTeamMemberDialog } from "@/components/dashboard/add-team-member-dialog";
import { useTeamMembers, type TeamMember } from "@/hooks/useTeamMembers";
import { useAuthFetch } from "@/hooks/useAuthToken";
import { useToast } from "@/hooks/use-toast";
import { Loader2, Plus, Trash2 } from "lucide-react";

// Simple spinner component
const Spinner = () => (
  <div className="mx-auto my-8 h-8 w-8 animate-spin rounded-full border-b-2 border-primary"></div>
);

export default function TeamPage() {
  const { teamMembers, viewer, isLoading, error, mutate } = useTeamMembers();
  const { fetchWithAuth } = useAuthFetch();
  const { toast } = useToast();
  const [pendingRemoval, setPendingRemoval] = useState<TeamMember | null>(null);
  const [isRemoving, setIsRemoving] = useState(false);

  // Generate avatar initials from name
  const getAvatarInitials = (name: string) => {
    return name
      .split(" ")
      .map((word) => word.charAt(0))
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  const canRemove = (member: TeamMember) =>
    viewer?.canRemove === true && member.id !== viewer.uid;

  const confirmRemoval = async () => {
    if (!pendingRemoval) return;
    const member = pendingRemoval;
    setIsRemoving(true);
    try {
      const response = await fetchWithAuth("/api/omi/team-members", {
        method: "DELETE",
        body: JSON.stringify({ uid: member.id }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "Failed to remove person");
      }
      await mutate();
      toast({
        title: "Access removed",
        description: `${member.email} no longer has admin dashboard access.`,
      });
      setPendingRemoval(null);
    } catch (err) {
      toast({
        title: "Could not remove person",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsRemoving(false);
    }
  };

  const header = (
    <div className="flex items-center justify-between gap-4">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Team Members</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          People with access to the Omi admin dashboard.
        </p>
      </div>
      <AddTeamMemberDialog onMemberAdded={async () => void (await mutate())}>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Add new person
        </Button>
      </AddTeamMemberDialog>
    </div>
  );

  if (isLoading) {
    return (
      <div className="space-y-6 p-6">
        {header}
        <div className="flex min-h-[300px] items-center justify-center">
          <Spinner />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6 p-6">
        {header}
        <div className="py-10 text-center text-red-500">
          Error loading team members: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      {header}

      {teamMembers.length === 0 ? (
        <div className="py-10 text-center text-muted-foreground">
          No team members found.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {teamMembers.map((member) => (
            <Card key={member.id}>
              <CardHeader className="flex flex-row items-center gap-4">
                <Avatar>
                  <AvatarFallback>
                    {getAvatarInitials(member.name)}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <CardTitle className="text-lg">{member.name}</CardTitle>
                  <CardDescription className="flex items-center gap-2">
                    {member.role}
                    {member.owner ? (
                      <Badge variant="secondary">Owner</Badge>
                    ) : null}
                  </CardDescription>
                </div>
                {canRemove(member) ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove ${member.name}`}
                    title="Remove admin access"
                    onClick={() => setPendingRemoval(member)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                ) : null}
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{member.email}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <AlertDialog
        open={pendingRemoval !== null}
        onOpenChange={(open) => {
          if (!open && !isRemoving) setPendingRemoval(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Remove {pendingRemoval?.name ?? "this person"}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingRemoval?.email} loses access to the admin dashboard
              immediately. You can add them back later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isRemoving}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={isRemoving}
              onClick={(event) => {
                event.preventDefault();
                void confirmRemoval();
              }}
            >
              {isRemoving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Remove access
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
