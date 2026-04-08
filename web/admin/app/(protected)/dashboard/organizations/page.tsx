"use client";

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useOrganizations, CreateOrganizationData, UpdateOrganizationData } from '@/hooks/useOrganizations';
import { Building2, Plus, Users, Globe, Calendar, Mail, Edit, CreditCard } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

export default function OrganizationsPage() {
  const { organizations, loading, error, createOrganization, toggleOrganizationStatus, updateOrganization } = useOrganizations();
  const { toast } = useToast();
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [formData, setFormData] = useState<CreateOrganizationData>({
    organisation_name: '',
    website: '',
    admin_name: '',
    admin_email: '',
    max_seats: undefined,
    stripe_payment_id: '',
  });
  
  // Edit dialog state
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [editingOrgId, setEditingOrgId] = useState<string | null>(null);
  const [editFormData, setEditFormData] = useState<UpdateOrganizationData>({
    organisation_name: '',
    website: '',
    max_seats: undefined,
    is_active: true,
    stripe_payment_id: '',
  });

  const handleCreateOrganization = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsCreating(true);

    try {
      await createOrganization(formData);
      // Only close dialog and reset form on success
      setIsCreateDialogOpen(false);
      setFormData({
        organisation_name: '',
        website: '',
        admin_name: '',
        admin_email: '',
        max_seats: undefined,
        stripe_payment_id: '',
      });
      toast({
        title: "Success",
        description: "Organization created successfully",
      });
    } catch (error) {
      // Show error but keep dialog open so user can fix the email
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to create organization",
        variant: "destructive",
        duration: 6000, // Show for 6 seconds
      });
      // Don't close the dialog - let user fix the error
    } finally {
      setIsCreating(false);
    }
  };

  const handleToggleStatus = async (organizationId: string, currentStatus: boolean) => {
    try {
      await toggleOrganizationStatus(organizationId, !currentStatus);
      toast({
        title: "Success",
        description: `Organization ${!currentStatus ? 'enabled' : 'disabled'} successfully`,
      });
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to update organization",
        variant: "destructive",
      });
    }
  };

  const handleEditOrganization = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingOrgId) return;
    
    setIsUpdating(true);
    try {
      await updateOrganization(editingOrgId, editFormData);
      setIsEditDialogOpen(false);
      setEditingOrgId(null);
      setEditFormData({
        organisation_name: '',
        website: '',
        max_seats: undefined,
        is_active: true,
        stripe_payment_id: '',
      });
      toast({
        title: "Success",
        description: "Organization updated successfully",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to update organization",
        variant: "destructive",
      });
    } finally {
      setIsUpdating(false);
    }
  };

  const openEditDialog = (org: any) => {
    setEditingOrgId(org.id);
    setEditFormData({
      organisation_name: org.organisation_name || '',
      website: org.website || '',
      max_seats: org.max_seats || undefined,
      is_active: org.is_active !== false,
      stripe_payment_id: org.subscription?.subscription_id || '',
    });
    setIsEditDialogOpen(true);
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const getRoleBadgeVariant = (role: string) => {
    switch (role) {
      case 'owner':
        return 'default';
      case 'admin':
        return 'secondary';
      case 'member':
        return 'outline';
      default:
        return 'outline';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-2 text-muted-foreground">Loading organizations...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <p className="text-destructive">Error: {error}</p>
          <Button onClick={() => window.location.reload()} className="mt-2">
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Organizations</h1>
          <p className="text-muted-foreground">
            Manage organizations and their members
          </p>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Add Organization
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[600px]">
            <form onSubmit={handleCreateOrganization}>
              <DialogHeader>
                <DialogTitle>Create New Organization</DialogTitle>
                <DialogDescription>
                  Add a new organization with an admin user. The admin user must already exist in the system.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-6 py-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="grid gap-2">
                    <Label htmlFor="org-name">
                      Organization Name *
                    </Label>
                    <Input
                      id="org-name"
                      value={formData.organisation_name}
                      onChange={(e) => setFormData({ ...formData, organisation_name: e.target.value })}
                      placeholder="Enter organization name"
                      required
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="website">
                      Website
                    </Label>
                    <Input
                      id="website"
                      type="url"
                      value={formData.website}
                      onChange={(e) => setFormData({ ...formData, website: e.target.value })}
                      placeholder="https://example.com"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="grid gap-2">
                    <Label htmlFor="admin-name">
                      Admin Name *
                    </Label>
                    <Input
                      id="admin-name"
                      value={formData.admin_name}
                      onChange={(e) => setFormData({ ...formData, admin_name: e.target.value })}
                      placeholder="Enter admin full name"
                      required
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="admin-email">
                      Admin Email *
                    </Label>
                    <Input
                      id="admin-email"
                      type="email"
                      value={formData.admin_email}
                      onChange={(e) => setFormData({ ...formData, admin_email: e.target.value })}
                      placeholder="admin@example.com"
                      required
                    />
                  </div>
                </div>
                <p className="text-sm text-muted-foreground">
                  The admin user must already exist in the OMI app
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="grid gap-2">
                    <Label htmlFor="max-seats">
                      Max Seats
                    </Label>
                    <Input
                      id="max-seats"
                      type="number"
                      min="0"
                      value={formData.max_seats || ''}
                      onChange={(e) => setFormData({ 
                        ...formData, 
                        max_seats: e.target.value ? parseInt(e.target.value) : undefined 
                      })}
                      placeholder="Leave empty for unlimited"
                    />
                    <p className="text-sm text-muted-foreground">
                      Maximum number of employees allowed
                    </p>
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="stripe-payment-id">
                      Stripe Payment ID
                    </Label>
                    <Input
                      id="stripe-payment-id"
                      value={formData.stripe_payment_id}
                      onChange={(e) => setFormData({ ...formData, stripe_payment_id: e.target.value })}
                      placeholder="pi_xxxxxxxxxxxxxxxx"
                    />
                    <p className="text-sm text-muted-foreground">
                      Automatically fetch payment details and calculate 1-year access
                    </p>
                  </div>
                </div>
              </div>
              <DialogFooter className="gap-2">
                <Button 
                  type="button" 
                  variant="outline" 
                  onClick={() => setIsCreateDialogOpen(false)}
                  disabled={isCreating}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating ? 'Creating...' : 'Create Organization'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
        
        {/* Edit Organization Dialog */}
        <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
          <DialogContent className="sm:max-w-[600px]">
            <form onSubmit={handleEditOrganization}>
              <DialogHeader>
                <DialogTitle>Edit Organization</DialogTitle>
                <DialogDescription>
                  Update organization details. Employee information cannot be edited here.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-6 py-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="grid gap-2">
                    <Label htmlFor="edit-org-name">
                      Organization Name *
                    </Label>
                    <Input
                      id="edit-org-name"
                      value={editFormData.organisation_name}
                      onChange={(e) => setEditFormData({ ...editFormData, organisation_name: e.target.value })}
                      placeholder="Enter organization name"
                      required
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="edit-website">
                      Website
                    </Label>
                    <Input
                      id="edit-website"
                      type="url"
                      value={editFormData.website}
                      onChange={(e) => setEditFormData({ ...editFormData, website: e.target.value })}
                      placeholder="https://example.com"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="grid gap-2">
                    <Label htmlFor="edit-max-seats">
                      Max Seats
                    </Label>
                    <Input
                      id="edit-max-seats"
                      type="number"
                      min="0"
                      value={editFormData.max_seats || ''}
                      onChange={(e) => setEditFormData({ 
                        ...editFormData, 
                        max_seats: e.target.value ? parseInt(e.target.value) : undefined 
                      })}
                      placeholder="Leave empty for unlimited"
                    />
                    <p className="text-sm text-muted-foreground">
                      Maximum number of employees allowed
                    </p>
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="edit-stripe-payment-id">
                      Stripe Payment ID
                    </Label>
                    <Input
                      id="edit-stripe-payment-id"
                      value={editFormData.stripe_payment_id}
                      onChange={(e) => setEditFormData({ ...editFormData, stripe_payment_id: e.target.value })}
                      placeholder="pi_xxxxxxxxxxxxxxxx"
                    />
                    <p className="text-sm text-muted-foreground">
                      1-year access from when the payment was made
                    </p>
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  <Switch
                    id="edit-is-active"
                    checked={editFormData.is_active}
                    onCheckedChange={(checked) => setEditFormData({ ...editFormData, is_active: checked })}
                  />
                  <Label htmlFor="edit-is-active">Active Organization</Label>
                </div>
              </div>
              <DialogFooter className="gap-2">
                <Button 
                  type="button" 
                  variant="outline" 
                  onClick={() => setIsEditDialogOpen(false)}
                  disabled={isUpdating}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isUpdating}>
                  {isUpdating ? 'Updating...' : 'Update Organization'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid gap-6">
        {organizations.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Building2 className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">No Organizations</h3>
              <p className="text-muted-foreground text-center mb-4">
                Get started by creating your first organization
              </p>
              <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
                <DialogTrigger asChild>
                  <Button>
                    <Plus className="h-4 w-4 mr-2" />
                    Add Organization
                  </Button>
                </DialogTrigger>
              </Dialog>
            </CardContent>
          </Card>
        ) : (
          organizations.map((org) => (
            <Card key={org.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <Building2 className="h-6 w-6 text-primary" />
                    <div>
                      <CardTitle className="text-xl">{org.organisation_name}</CardTitle>
                      <CardDescription className="flex items-center space-x-4 mt-1">
                        {org.website && (
                          <span className="flex items-center">
                            <Globe className="h-4 w-4 mr-1" />
                            <a 
                              href={org.website} 
                              target="_blank" 
                              rel="noopener noreferrer"
                              className="text-primary hover:underline"
                            >
                              {org.website}
                            </a>
                          </span>
                        )}
                        <span className="flex items-center">
                          <Calendar className="h-4 w-4 mr-1" />
                          Created {formatDate(org.added_on)}
                        </span>
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openEditDialog(org)}
                    >
                      <Edit className="h-4 w-4 mr-2" />
                      Edit
                    </Button>
                    <Badge variant={org.is_active !== false ? "default" : "secondary"}>
                      {org.is_active !== false ? "Active" : "Inactive"}
                    </Badge>
                    <Switch
                      checked={org.is_active !== false}
                      onCheckedChange={(checked) => handleToggleStatus(org.id, !checked)}
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-center space-x-4">
                    <div className="flex items-center space-x-2">
                      <Users className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">
                        {org.employees.length} Employee{org.employees.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                    {org.max_seats && (
                      <div className="flex items-center space-x-2">
                        <span className="text-sm text-muted-foreground">
                          {org.employees.length}/{org.max_seats} seats used
                        </span>
                      </div>
                    )}
                    {org.subscription && (
                      <div className="flex items-center space-x-2">
                        <CreditCard className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm text-muted-foreground">
                          {org.subscription.plan} plan - {org.subscription.status}
                        </span>
                      </div>
                    )}
                  </div>
                  
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Email</TableHead>
                        <TableHead>Role</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Added</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {org.employees.map((employee, index) => (
                        <TableRow key={index}>
                          <TableCell className="flex items-center">
                            <Mail className="h-4 w-4 mr-2 text-muted-foreground" />
                            {employee.email}
                          </TableCell>
                          <TableCell>
                            <Badge variant={getRoleBadgeVariant(employee.role)}>
                              {employee.role}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={employee.is_active ? "default" : "secondary"}>
                              {employee.is_active ? "Active" : "Inactive"}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {formatDate(employee.added_at)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
