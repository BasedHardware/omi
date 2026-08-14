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

interface AddTeamMemberDialogProps {
  children: ReactNode;
  onMemberAdded: () => void | Promise<void>;
}

export function AddTeamMemberDialog({
  children,
  onMemberAdded,
}: AddTeamMemberDialogProps) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { toast } = useToast();
  const { fetchWithAuth } = useAuthFetch();

  const close = () => {
    setOpen(false);
    setEmail("");
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) return;

    setIsSubmitting(true);
    try {
      const response = await fetchWithAuth("/api/omi/team-members", {
        method: "POST",
        body: JSON.stringify({ email: normalizedEmail }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "Failed to add person");
      }

      await onMemberAdded();
      toast({
        title: "Person added",
        description: `${normalizedEmail} now has admin dashboard access.`,
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
        if (!nextOpen) setEmail("");
      }}
    >
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-[440px]">
        <form onSubmit={handleSubmit} className="space-y-5">
          <DialogHeader>
            <DialogTitle>Add new person</DialogTitle>
            <DialogDescription>
              Grant admin dashboard access to an existing Omi user. They must
              have signed in to Omi at least once.
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
