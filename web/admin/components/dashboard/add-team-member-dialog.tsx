"use client";

import { FormEvent, ReactNode, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { useAuthFetch } from "@/hooks/useAuthToken";
import { ROLES, ROLE_IDS, type RoleId } from "@/lib/admin-access";

interface AddTeamMemberDialogProps {
  children: ReactNode;
  /** Only an owner may appoint deputies. */
  isOwner?: boolean;
  onMemberAdded: () => void | Promise<void>;
}

export function AddTeamMemberDialog({
  children,
  isOwner = false,
  onMemberAdded,
}: AddTeamMemberDialogProps) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [accessRole, setAccessRole] = useState<RoleId>("viewer");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { toast } = useToast();
  const { fetchWithAuth } = useAuthFetch();

  const close = () => {
    setOpen(false);
    setEmail("");
    setAccessRole("viewer");
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) return;

    setIsSubmitting(true);
    try {
      const response = await fetchWithAuth("/api/omi/team-members", {
        method: "POST",
        body: JSON.stringify({ email: normalizedEmail, accessRole }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.error || "Failed to add person");
      }

      await onMemberAdded();
      toast({
        title:
          data.emailSent === false
            ? "Added, but the invite email failed to send"
            : "Person added",
        description:
          data.emailSent === false
            ? `${normalizedEmail} now has admin dashboard access. Tell them to sign in with Google using this email.`
            : data.provisioned
            ? `${normalizedEmail} now has admin dashboard access. We emailed them to sign in with Google using this email.`
            : `${normalizedEmail} now has admin dashboard access. We emailed them the sign-in details.`,
      });
      close();
    } catch (error) {
      toast({
        title: "Could not add person",
        description:
          error instanceof Error ? error.message : "Failed to add person",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen) {
          setEmail("");
          setAccessRole("viewer");
        }
      }}
    >
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-[440px]">
        <form onSubmit={handleSubmit} className="space-y-5">
          <DialogHeader>
            <DialogTitle>Add new person</DialogTitle>
            <DialogDescription>
              Grant admin dashboard access by email. They sign in with Google
              using this address. An Omi account is not required first.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="team-member-email">Email</Label>
            <Input
              id="team-member-email"
              type="email"
              placeholder="person@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              autoFocus
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="team-member-role">Role</Label>
            <select
              id="team-member-role"
              className="h-10 w-full rounded-md border bg-background px-3 text-sm"
              value={accessRole}
              onChange={(event) => setAccessRole(event.target.value as RoleId)}
            >
              {ROLE_IDS.filter((id) => id !== "deputy" || isOwner).map((id) => (
                <option key={id} value={id}>
                  {ROLES[id].label}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              You can grant a role no broader than your own.
            </p>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={close}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || !email.trim()}>
              {isSubmitting ? (
                <Loader2
                  className="h-4 w-4 animate-spin"
                  aria-label="Adding person"
                />
              ) : (
                "Add person"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
