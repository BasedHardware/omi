"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { AddTeamMemberDialog } from "@/components/dashboard/add-team-member-dialog";
import { useTeamMembers } from "@/hooks/useTeamMembers";
import { Plus } from "lucide-react";

// Simple spinner component
const Spinner = () => (
  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto my-8"></div>
);

export default function TeamPage() {
  const { teamMembers, isLoading, error, mutate } = useTeamMembers();

  // Generate avatar initials from name
  const getAvatarInitials = (name: string) => {
    return name
      .split(" ")
      .map((word) => word.charAt(0))
      .join("")
      .toUpperCase()
      .slice(0, 2);
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
      <div className="p-6 space-y-6">
        {header}
        <div className="flex items-center justify-center min-h-[300px]">
          <Spinner />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 space-y-6">
        {header}
        <div className="text-red-500 text-center py-10">
          Error loading team members: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {header}

      {teamMembers.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">
          No team members found.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {teamMembers.map((member) => (
            <Card key={member.id}>
              <CardHeader className="flex flex-row items-center gap-4">
                <Avatar>
                  <AvatarFallback>
                    {getAvatarInitials(member.name)}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <CardTitle className="text-lg">{member.name}</CardTitle>
                  <CardDescription>{member.role}</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{member.email}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
