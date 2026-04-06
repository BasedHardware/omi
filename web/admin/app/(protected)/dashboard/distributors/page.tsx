'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useDistributors, CreateDistributorData } from '@/hooks/useDistributors'
import { Distributor, REGIONS, COUNTRY_NAMES } from '@/types/distributor'
import CountryPicker from '@/components/common/CountryPicker'
import { Plus, Edit, Truck, MapPin } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'

const emptyForm: CreateDistributorData = {
  email: '',
  name: '',
  isActive: true,
  isAdmin: false,
  countries: [],
  locationId: '',
  locationName: '',
}

function getCountryDisplay(countries: string[]) {
  if (!countries || countries.length === 0) return null

  const regionSummary: string[] = []
  const individualCountries: string[] = []

  for (const region of REGIONS) {
    const selectedInRegion = region.countries.filter((c) => countries.includes(c))
    if (selectedInRegion.length === region.countries.length) {
      regionSummary.push(region.code)
    } else if (selectedInRegion.length > 0) {
      individualCountries.push(...selectedInRegion)
    }
  }

  const allRegionCountries = REGIONS.flatMap((r) => [...r.countries])
  const otherCountries = countries.filter((c) => !allRegionCountries.includes(c))
  individualCountries.push(...otherCountries)

  return { regionSummary, individualCountries }
}

function renderFormFields(
  formData: CreateDistributorData,
  setFormData: (data: CreateDistributorData) => void,
  locations: { id: string; name: string; isActive: boolean }[],
  isEditing: boolean,
  isSubmitting: boolean,
) {
  return (
    <div className="grid gap-6 py-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="grid gap-2">
          <Label htmlFor={isEditing ? 'edit-dist-email' : 'create-dist-email'}>Email *</Label>
          <Input
            id={isEditing ? 'edit-dist-email' : 'create-dist-email'}
            type="email"
            value={formData.email}
            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            placeholder="distributor@example.com"
            required
            disabled={isEditing}
          />
          {isEditing && (
            <p className="text-xs text-muted-foreground">Email cannot be changed after creation</p>
          )}
        </div>
        <div className="grid gap-2">
          <Label htmlFor={isEditing ? 'edit-dist-name' : 'create-dist-name'}>Name *</Label>
          <Input
            id={isEditing ? 'edit-dist-name' : 'create-dist-name'}
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="Enter distributor name"
            required
          />
        </div>
      </div>

      <div className="flex items-center space-x-6">
        <div className="flex items-center space-x-2">
          <Switch
            id={isEditing ? 'edit-dist-active' : 'create-dist-active'}
            checked={formData.isActive}
            onCheckedChange={(checked) => setFormData({ ...formData, isActive: checked })}
          />
          <Label htmlFor={isEditing ? 'edit-dist-active' : 'create-dist-active'}>Active</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch
            id={isEditing ? 'edit-dist-admin' : 'create-dist-admin'}
            checked={formData.isAdmin}
            onCheckedChange={(checked) => setFormData({ ...formData, isAdmin: checked })}
          />
          <Label htmlFor={isEditing ? 'edit-dist-admin' : 'create-dist-admin'}>Admin</Label>
        </div>
      </div>

      <div className="grid gap-2">
        <Label>Fulfillment Location</Label>
        <Select
          value={formData.locationId || '_none'}
          onValueChange={(value) => setFormData({ ...formData, locationId: value === '_none' ? '' : value })}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select a warehouse" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="_none">No warehouse assigned</SelectItem>
            {locations.map((loc) => (
              <SelectItem key={loc.id} value={loc.id}>
                {loc.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Shopify fulfillment location for this distributor&apos;s orders and inventory
        </p>
      </div>

      <div className="grid gap-2">
        <Label>Assigned Countries</Label>
        <CountryPicker
          selectedCountries={formData.countries}
          onChange={(countries) => setFormData({ ...formData, countries })}
          disabled={isSubmitting}
        />
        <p className="text-xs text-muted-foreground">
          Select regions or individual countries this distributor handles
        </p>
      </div>
    </div>
  )
}

export default function DistributorsPage() {
  const { distributors, locations, loading, error, createDistributor, updateDistributor } = useDistributors()
  const { toast } = useToast()

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [formData, setFormData] = useState<CreateDistributorData>({ ...emptyForm })

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    try {
      const selectedLocation = locations.find((l) => l.id === formData.locationId)
      await createDistributor({
        ...formData,
        locationName: selectedLocation?.name || '',
      })
      setIsCreateDialogOpen(false)
      setFormData({ ...emptyForm })
      toast({ title: 'Success', description: 'Distributor created successfully' })
    } catch (err) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to create distributor',
        variant: 'destructive',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingId) return
    setIsSubmitting(true)
    try {
      const selectedLocation = locations.find((l) => l.id === formData.locationId)
      await updateDistributor({
        id: editingId,
        ...formData,
        locationName: selectedLocation?.name || '',
      })
      setIsEditDialogOpen(false)
      setEditingId(null)
      setFormData({ ...emptyForm })
      toast({ title: 'Success', description: 'Distributor updated successfully' })
    } catch (err) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to update distributor',
        variant: 'destructive',
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const openEditDialog = (dist: Distributor) => {
    setEditingId(dist.id)
    setFormData({
      email: dist.email,
      name: dist.name,
      isActive: dist.isActive,
      isAdmin: dist.isAdmin,
      countries: dist.countries || [],
      locationId: dist.locationId || '',
      locationName: dist.locationName || '',
    })
    setIsEditDialogOpen(true)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto" />
          <p className="mt-2 text-muted-foreground">Loading distributors...</p>
        </div>
      </div>
    )
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
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Distributors</h1>
          <p className="text-muted-foreground">
            Manage distributors, their fulfillment locations, and assigned countries
          </p>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={() => setFormData({ ...emptyForm })}>
              <Plus className="h-4 w-4 mr-2" />
              Add Distributor
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Add New Distributor</DialogTitle>
              <DialogDescription>
                Create a new distributor account. They must sign in via Google or Apple OAuth after being registered.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreate}>
              {renderFormFields(formData, setFormData, locations, false, isSubmitting)}
              <DialogFooter className="gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setIsCreateDialogOpen(false)
                    setFormData({ ...emptyForm })
                  }}
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Saving...' : 'Create Distributor'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
          <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Edit Distributor</DialogTitle>
              <DialogDescription>
                Update distributor details. Email cannot be changed after creation.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleEdit}>
              {renderFormFields(formData, setFormData, locations, true, isSubmitting)}
              <DialogFooter className="gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setIsEditDialogOpen(false)
                    setFormData({ ...emptyForm })
                    setEditingId(null)
                  }}
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Saving...' : 'Update Distributor'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {distributors.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center border rounded-lg bg-card">
          <Truck className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">No Distributors</h3>
          <p className="text-muted-foreground">
            Get started by adding your first distributor using the button above
          </p>
        </div>
      ) : (
        <div className="border rounded-lg bg-card overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Countries</TableHead>
                <TableHead>Warehouse</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {distributors.map((dist) => {
                const countryDisplay = getCountryDisplay(dist.countries)
                return (
                  <TableRow key={dist.id}>
                    <TableCell className="font-medium">{dist.name}</TableCell>
                    <TableCell className="text-muted-foreground">{dist.email}</TableCell>
                    <TableCell>
                      <Badge variant={dist.isActive ? 'default' : 'secondary'}>
                        {dist.isActive ? 'Active' : 'Inactive'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={dist.isAdmin ? 'default' : 'outline'}>
                        {dist.isAdmin ? 'Admin' : 'Distributor'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {countryDisplay ? (
                        <div className="flex flex-wrap gap-1 max-w-xs">
                          {countryDisplay.regionSummary.map((r) => (
                            <Badge key={r} variant="secondary" className="text-xs">
                              {r}
                            </Badge>
                          ))}
                          {countryDisplay.individualCountries.slice(0, 5).map((c) => (
                            <Badge key={c} variant="outline" className="text-xs">
                              {c}
                            </Badge>
                          ))}
                          {countryDisplay.individualCountries.length > 5 && (
                            <span className="text-xs text-muted-foreground">
                              +{countryDisplay.individualCountries.length - 5} more
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">None</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {dist.locationName ? (
                        <span className="flex items-center gap-1 text-sm">
                          <MapPin className="h-3 w-3 text-muted-foreground" />
                          {dist.locationName}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm" onClick={() => openEditDialog(dist)}>
                        <Edit className="h-4 w-4 mr-1" />
                        Edit
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
