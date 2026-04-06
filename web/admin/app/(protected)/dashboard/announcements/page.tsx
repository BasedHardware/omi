'use client';

import React, { useState } from 'react';
import { useAnnouncements, Announcement, AnnouncementType, CreateAnnouncementData, ChangelogContent, FeatureContent, AnnouncementContent, ChangelogItem, FeatureStep, AnnouncementTargeting, AnnouncementDisplay, TriggerType, PlatformType } from '@/hooks/useAnnouncements';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Plus, Trash2, Edit, Eye, EyeOff, Megaphone, FileText, Sparkles, X, Target, Settings2, Smartphone } from 'lucide-react';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { ImageUpload } from '@/components/ui/image-upload';
import { uploadImage } from '@/lib/utils/upload';

const Spinner = () => (
  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto my-8" />
);

// Type-specific icons
const getTypeIcon = (type: AnnouncementType) => {
  switch (type) {
    case 'changelog':
      return <FileText className="h-4 w-4" />;
    case 'feature':
      return <Sparkles className="h-4 w-4" />;
    case 'announcement':
      return <Megaphone className="h-4 w-4" />;
  }
};

const getTypeBadgeVariant = (type: AnnouncementType) => {
  switch (type) {
    case 'changelog':
      return 'secondary';
    case 'feature':
      return 'default';
    case 'announcement':
      return 'outline';
  }
};

// Announcement card component
function AnnouncementCard({
  announcement,
  onToggleActive,
  onDelete,
  onEdit,
}: {
  announcement: Announcement;
  onToggleActive: (id: string, active: boolean) => void;
  onDelete: (id: string) => void;
  onEdit: (announcement: Announcement) => void;
}) {
  const content = announcement.content as any;

  // Check if advanced targeting is configured
  const hasAdvancedTargeting = announcement.targeting && (
    announcement.targeting.app_version_min ||
    announcement.targeting.app_version_max ||
    announcement.targeting.firmware_version_min ||
    announcement.targeting.firmware_version_max ||
    announcement.targeting.platforms?.length ||
    (announcement.targeting.trigger && announcement.targeting.trigger !== 'version_upgrade')
  );

  // Check if in test mode (has test_uids)
  const isTestMode = announcement.targeting?.test_uids && announcement.targeting.test_uids.length > 0;

  return (
    <Card className={!announcement.active ? 'opacity-60' : ''}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={getTypeBadgeVariant(announcement.type)} className="capitalize">
              {getTypeIcon(announcement.type)}
              <span className="ml-1">{announcement.type}</span>
            </Badge>
            {announcement.app_version && (
              <Badge variant="outline">v{announcement.app_version}</Badge>
            )}
            {announcement.firmware_version && (
              <Badge variant="outline">FW {announcement.firmware_version}</Badge>
            )}
            {/* Show test mode indicator */}
            {isTestMode && (
              <Badge variant="outline" className="text-yellow-600 border-yellow-600 bg-yellow-500/10">
                Test Mode
              </Badge>
            )}
            {/* Show targeting indicator */}
            {hasAdvancedTargeting && !isTestMode && (
              <Badge variant="secondary">
                <Target className="h-3 w-3 mr-1" />
                Targeted
              </Badge>
            )}
            {/* Show priority if set */}
            {announcement.display?.priority && announcement.display.priority > 0 && (
              <Badge variant="secondary">
                Priority: {announcement.display.priority}
              </Badge>
            )}
            {/* Show platform badges */}
            {announcement.targeting?.platforms?.map(platform => (
              <Badge key={platform} variant="outline" className="capitalize">
                {platform}
              </Badge>
            ))}
            {!announcement.active && (
              <Badge variant="destructive">Inactive</Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onToggleActive(announcement.id, !announcement.active)}
              title={announcement.active ? 'Deactivate' : 'Activate'}
            >
              {announcement.active ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onEdit(announcement)}
            >
              <Edit className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onDelete(announcement.id)}
              className="text-destructive hover:text-destructive"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <CardTitle className="text-lg mt-2">{content.title}</CardTitle>
        <CardDescription>
          Created {format(new Date(announcement.created_at), 'MMM d, yyyy HH:mm')}
          {/* Show display.start_at if set */}
          {announcement.display?.start_at && (
            <> · Starts {format(new Date(announcement.display.start_at), 'MMM d, yyyy HH:mm')}</>
          )}
          {/* Use display.expires_at if available, fall back to legacy expires_at */}
          {(announcement.display?.expires_at || announcement.expires_at) && (
            <> · Expires {format(new Date(announcement.display?.expires_at || announcement.expires_at!), 'MMM d, yyyy')}</>
          )}
          {/* Show trigger type if not default */}
          {announcement.targeting?.trigger && announcement.targeting.trigger !== 'version_upgrade' && (
            <> · Trigger: {announcement.targeting.trigger}</>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {announcement.type === 'changelog' && (
          <div className="space-y-2">
            {(content as ChangelogContent).changes?.slice(0, 3).map((change, i) => (
              <div key={i} className="flex items-start gap-2 text-sm">
                <span>{change.icon || '•'}</span>
                <div>
                  <span className="font-medium">{change.title}</span>
                  <p className="text-muted-foreground line-clamp-1">{change.description}</p>
                </div>
              </div>
            ))}
            {(content as ChangelogContent).changes?.length > 3 && (
              <p className="text-xs text-muted-foreground">
                +{(content as ChangelogContent).changes.length - 3} more changes
              </p>
            )}
          </div>
        )}
        {announcement.type === 'feature' && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              {(content as FeatureContent).steps?.length || 0} steps
            </p>
            {(content as FeatureContent).steps?.[0] && (
              <p className="text-sm line-clamp-2">{(content as FeatureContent).steps[0].description}</p>
            )}
          </div>
        )}
        {announcement.type === 'announcement' && (
          <div className="space-y-2">
            <p className="text-sm line-clamp-2">{(content as AnnouncementContent).body}</p>
            {(content as AnnouncementContent).cta && (
              <Badge variant="secondary">CTA: {(content as AnnouncementContent).cta?.text}</Badge>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Create/Edit Dialog Component
function AnnouncementFormDialog({
  open,
  onOpenChange,
  onSubmit,
  editingAnnouncement,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: CreateAnnouncementData) => Promise<void>;
  editingAnnouncement?: Announcement | null;
}) {
  const [type, setType] = useState<AnnouncementType>(editingAnnouncement?.type || 'changelog');
  const [deviceModels, setDeviceModels] = useState(editingAnnouncement?.device_models?.join(', ') || '');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Changelog state
  const [changelogTitle, setChangelogTitle] = useState('');
  const [changes, setChanges] = useState<ChangelogItem[]>([{ title: '', description: '', icon: '' }]);

  // Feature state
  const [featureTitle, setFeatureTitle] = useState('');
  const [steps, setSteps] = useState<FeatureStep[]>([{ title: '', description: '' }]);
  // Pending files for feature steps (deferred upload)
  const [stepPendingFiles, setStepPendingFiles] = useState<(File | null)[]>([null]);

  // Announcement state
  const [announcementTitle, setAnnouncementTitle] = useState('');
  const [announcementBody, setAnnouncementBody] = useState('');
  const [announcementImageUrl, setAnnouncementImageUrl] = useState('');
  const [announcementPendingFile, setAnnouncementPendingFile] = useState<File | null>(null);
  const [ctaText, setCtaText] = useState('');
  const [ctaAction, setCtaAction] = useState('');

  // Advanced Targeting state
  const [appVersionMin, setAppVersionMin] = useState('');
  const [appVersionMax, setAppVersionMax] = useState('');
  const [firmwareVersionMin, setFirmwareVersionMin] = useState('');
  const [firmwareVersionMax, setFirmwareVersionMax] = useState('');
  const [platforms, setPlatforms] = useState<PlatformType[]>([]);
  const [trigger, setTrigger] = useState<TriggerType>('version_upgrade');
  const [testUids, setTestUids] = useState('');

  // Display Options state
  const [priority, setPriority] = useState(0);
  const [startAt, setStartAt] = useState('');
  const [displayExpiresAt, setDisplayExpiresAt] = useState('');
  const [dismissible, setDismissible] = useState(true);
  const [showOnce, setShowOnce] = useState(true);

  const resetForm = () => {
    setType('changelog');
    setDeviceModels('');
    setChangelogTitle('');
    setChanges([{ title: '', description: '', icon: '' }]);
    setFeatureTitle('');
    setSteps([{ title: '', description: '' }]);
    setStepPendingFiles([null]);
    setAnnouncementTitle('');
    setAnnouncementBody('');
    setAnnouncementImageUrl('');
    setAnnouncementPendingFile(null);
    setCtaText('');
    setCtaAction('');
    // Reset targeting fields
    setAppVersionMin('');
    setAppVersionMax('');
    setFirmwareVersionMin('');
    setFirmwareVersionMax('');
    setPlatforms([]);
    setTrigger('version_upgrade');
    setTestUids('');
    // Reset display fields
    setPriority(0);
    setStartAt('');
    setDisplayExpiresAt('');
    setDismissible(true);
    setShowOnce(true);
  };

  // Initialize form when editing or reset when creating new
  React.useEffect(() => {
    if (editingAnnouncement) {
      setType(editingAnnouncement.type);
      // Populate device models from targeting or legacy field
      setDeviceModels(editingAnnouncement.targeting?.device_models?.join(', ') || editingAnnouncement.device_models?.join(', ') || '');

      // Populate targeting fields
      const targeting = editingAnnouncement.targeting;
      setAppVersionMin(targeting?.app_version_min || '');
      setAppVersionMax(targeting?.app_version_max || '');
      setFirmwareVersionMin(targeting?.firmware_version_min || '');
      setFirmwareVersionMax(targeting?.firmware_version_max || '');
      setPlatforms(targeting?.platforms || []);
      setTrigger(targeting?.trigger || 'version_upgrade');
      setTestUids(targeting?.test_uids?.join(', ') || '');

      // Populate display fields
      const display = editingAnnouncement.display;
      setPriority(display?.priority || 0);
      setStartAt(display?.start_at ? display.start_at.slice(0, 16) : '');
      setDisplayExpiresAt(display?.expires_at ? display.expires_at.slice(0, 16) : '');
      setDismissible(display?.dismissible !== false);
      setShowOnce(display?.show_once !== false);

      const content = editingAnnouncement.content as any;
      if (editingAnnouncement.type === 'changelog') {
        setChangelogTitle(content.title || '');
        setChanges(content.changes || [{ title: '', description: '', icon: '' }]);
      } else if (editingAnnouncement.type === 'feature') {
        setFeatureTitle(content.title || '');
        const stepsData = content.steps || [{ title: '', description: '' }];
        setSteps(stepsData);
        setStepPendingFiles(stepsData.map(() => null));
      } else {
        setAnnouncementTitle(content.title || '');
        setAnnouncementBody(content.body || '');
        setAnnouncementImageUrl(content.image_url || '');
        setAnnouncementPendingFile(null);
        setCtaText(content.cta?.text || '');
        setCtaAction(content.cta?.action || '');
      }
    } else if (open) {
      // Reset form when opening for new announcement
      resetForm();
    }
  }, [editingAnnouncement, open]);

  const handleSubmit = async () => {
    let content: ChangelogContent | FeatureContent | AnnouncementContent;

    setIsSubmitting(true);
    try {
      if (type === 'changelog') {
        if (!changelogTitle || changes.some(c => !c.title || !c.description || !c.icon)) {
          toast.error('Please fill in all changelog fields including icon');
          setIsSubmitting(false);
          return;
        }
        content = {
          title: changelogTitle,
          changes: changes.map(c => ({ title: c.title, description: c.description, icon: c.icon || undefined })),
        };
      } else if (type === 'feature') {
        if (!featureTitle || steps.some(s => !s.title || !s.description)) {
          toast.error('Please fill in all feature fields');
          setIsSubmitting(false);
          return;
        }
        
        // Upload pending step images
        const uploadedSteps = await Promise.all(
          steps.map(async (step, i) => {
            let imageUrl = step.image_url;
            const pendingFile = stepPendingFiles[i];
            if (pendingFile) {
              toast.loading(`Uploading image ${i + 1}...`, { id: `upload-${i}` });
              imageUrl = await uploadImage(pendingFile, 'announcements/features');
              toast.dismiss(`upload-${i}`);
            }
            return {
              title: step.title,
              description: step.description,
              image_url: imageUrl || undefined,
              video_url: step.video_url || undefined,
              highlight_text: step.highlight_text || undefined,
            };
          })
        );
        
        content = {
          title: featureTitle,
          steps: uploadedSteps,
        };
      } else {
        if (!announcementTitle || !announcementBody) {
          toast.error('Please fill in title and body');
          setIsSubmitting(false);
          return;
        }
        
        // Upload pending announcement image
        let finalImageUrl = announcementImageUrl;
        if (announcementPendingFile) {
          toast.loading('Uploading image...', { id: 'upload-announcement' });
          finalImageUrl = await uploadImage(announcementPendingFile, 'announcements/general');
          toast.dismiss('upload-announcement');
        }
        
        content = {
          title: announcementTitle,
          body: announcementBody,
          image_url: finalImageUrl || undefined,
          cta: ctaText && ctaAction ? { text: ctaText, action: ctaAction } : undefined,
        };
      }

      // Build targeting object if any targeting fields are set
      const testUidsArray = testUids ? testUids.split(',').map(s => s.trim()).filter(Boolean) : [];
      const hasTargeting = appVersionMin || appVersionMax || firmwareVersionMin ||
        firmwareVersionMax || platforms.length > 0 || trigger !== 'version_upgrade' || testUidsArray.length > 0;

      const targeting: AnnouncementTargeting | undefined = hasTargeting ? {
        app_version_min: appVersionMin || undefined,
        app_version_max: appVersionMax || undefined,
        firmware_version_min: firmwareVersionMin || undefined,
        firmware_version_max: firmwareVersionMax || undefined,
        device_models: deviceModels ? deviceModels.split(',').map(s => s.trim()).filter(Boolean) : undefined,
        platforms: platforms.length > 0 ? platforms : undefined,
        trigger: trigger,
        test_uids: testUidsArray.length > 0 ? testUidsArray : undefined,
      } : undefined;

      // Build display object if any display fields are set
      const hasDisplay = priority !== 0 || startAt || displayExpiresAt ||
        !dismissible || !showOnce;

      const display: AnnouncementDisplay | undefined = hasDisplay ? {
        priority: priority !== 0 ? priority : undefined,
        start_at: startAt ? new Date(startAt).toISOString() : undefined,
        expires_at: displayExpiresAt ? new Date(displayExpiresAt).toISOString() : undefined,
        dismissible: dismissible !== true ? dismissible : undefined,
        show_once: showOnce !== true ? showOnce : undefined,
      } : undefined;

      // Build legacy fields for backward compatibility with old app versions
      // Old apps look for app_version, firmware_version, device_models, expires_at at root level
      const legacyAppVersion = appVersionMin || undefined;
      const legacyFirmwareVersion = firmwareVersionMin || undefined;
      const legacyDeviceModels = deviceModels ? deviceModels.split(',').map(s => s.trim()).filter(Boolean) : undefined;
      const legacyExpiresAt = displayExpiresAt ? new Date(displayExpiresAt).toISOString() : undefined;

      const data: CreateAnnouncementData = {
        type,
        content,
        // Legacy fields for backward compatibility
        app_version: legacyAppVersion,
        firmware_version: legacyFirmwareVersion,
        device_models: legacyDeviceModels?.length ? legacyDeviceModels : undefined,
        expires_at: legacyExpiresAt,
        // New targeting and display fields
        targeting,
        display,
      };

      await onSubmit(data);
      resetForm();
      onOpenChange(false);
    } catch (err: any) {
      toast.error(err?.message || 'Failed to save announcement');
    } finally {
      setIsSubmitting(false);
    }
  };

  const addChange = () => setChanges([...changes, { title: '', description: '', icon: '' }]);
  const removeChange = (index: number) => setChanges(changes.filter((_, i) => i !== index));
  const updateChange = (index: number, field: keyof ChangelogItem, value: string) => {
    const updated = [...changes];
    updated[index] = { ...updated[index], [field]: value };
    setChanges(updated);
  };

  const addStep = () => {
    setSteps([...steps, { title: '', description: '' }]);
    setStepPendingFiles([...stepPendingFiles, null]);
  };
  const removeStep = (index: number) => {
    setSteps(steps.filter((_, i) => i !== index));
    setStepPendingFiles(stepPendingFiles.filter((_, i) => i !== index));
  };
  const updateStep = (index: number, field: keyof FeatureStep, value: string) => {
    const updated = [...steps];
    updated[index] = { ...updated[index], [field]: value };
    setSteps(updated);
  };
  const updateStepPendingFile = (index: number, file: File | null) => {
    const updated = [...stepPendingFiles];
    updated[index] = file;
    setStepPendingFiles(updated);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{editingAnnouncement ? 'Edit Announcement' : 'Create Announcement'}</DialogTitle>
          <DialogDescription>
            Create a new announcement to show users after app or firmware updates.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[60vh]">
          <div className="space-y-6 py-4 px-1">
            {/* Type Selection */}
            <div className="space-y-2">
              <Label>Announcement Type</Label>
              <Select value={type} onValueChange={(v) => setType(v as AnnouncementType)} disabled={!!editingAnnouncement}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="changelog">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4" />
                      Changelog - App version updates
                    </div>
                  </SelectItem>
                  <SelectItem value="feature">
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4" />
                      Feature - Major feature explanations
                    </div>
                  </SelectItem>
                  <SelectItem value="announcement">
                    <div className="flex items-center gap-2">
                      <Megaphone className="h-4 w-4" />
                      Announcement - General promos/notices
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Targeting Section */}
            <Accordion type="single" collapsible defaultValue="targeting" className="border rounded-lg">
              <AccordionItem value="targeting" className="border-0">
                <AccordionTrigger className="px-4 py-3 hover:no-underline">
                  <div className="flex items-center gap-2">
                    <Target className="h-4 w-4" />
                    <span>Targeting</span>
                  </div>
                </AccordionTrigger>
                <AccordionContent className="px-4 pb-4">
                  <div className="space-y-4">
                    {/* App Version Range */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label>App Version Min</Label>
                        <Input
                          placeholder="e.g., 1.0.500"
                          value={appVersionMin}
                          onChange={(e) => setAppVersionMin(e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">Show to users &gt;= this version</p>
                      </div>
                      <div className="space-y-2">
                        <Label>App Version Max</Label>
                        <Input
                          placeholder="e.g., 1.0.600"
                          value={appVersionMax}
                          onChange={(e) => setAppVersionMax(e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">Show to users &lt;= this version</p>
                      </div>
                    </div>

                    {/* Firmware Version Range */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label>Firmware Version Min</Label>
                        <Input
                          placeholder="e.g., 3.0.0"
                          value={firmwareVersionMin}
                          onChange={(e) => setFirmwareVersionMin(e.target.value)}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Firmware Version Max</Label>
                        <Input
                          placeholder="e.g., 3.99.99"
                          value={firmwareVersionMax}
                          onChange={(e) => setFirmwareVersionMax(e.target.value)}
                        />
                      </div>
                    </div>

                    {/* Device Models */}
                    <div className="space-y-2">
                      <Label>Device Models</Label>
                      <Input
                        placeholder="e.g., Omi DevKit 2, Friend"
                        value={deviceModels}
                        onChange={(e) => setDeviceModels(e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">Comma-separated. Leave empty to target all devices.</p>
                    </div>

                    {/* Platform targeting */}
                    <div className="space-y-2">
                      <Label>Platforms</Label>
                      <div className="flex gap-6">
                        <div className="flex items-center space-x-2">
                          <Checkbox
                            id="platform-ios"
                            checked={platforms.includes('ios')}
                            onCheckedChange={(checked) => {
                              if (checked) {
                                setPlatforms([...platforms, 'ios']);
                              } else {
                                setPlatforms(platforms.filter(p => p !== 'ios'));
                              }
                            }}
                          />
                          <Label htmlFor="platform-ios" className="flex items-center gap-1 cursor-pointer">
                            <Smartphone className="h-4 w-4" /> iOS
                          </Label>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Checkbox
                            id="platform-android"
                            checked={platforms.includes('android')}
                            onCheckedChange={(checked) => {
                              if (checked) {
                                setPlatforms([...platforms, 'android']);
                              } else {
                                setPlatforms(platforms.filter(p => p !== 'android'));
                              }
                            }}
                          />
                          <Label htmlFor="platform-android" className="flex items-center gap-1 cursor-pointer">
                            <Smartphone className="h-4 w-4" /> Android
                          </Label>
                        </div>
                      </div>
                      <p className="text-xs text-muted-foreground">Leave empty to target all platforms</p>
                    </div>

                    {/* Trigger type */}
                    <div className="space-y-2">
                      <Label>Trigger</Label>
                      <Select value={trigger} onValueChange={(v) => setTrigger(v as TriggerType)}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="immediate">
                            Immediate - Show on every app launch
                          </SelectItem>
                          <SelectItem value="version_upgrade">
                            Version Upgrade - Show when app version changes
                          </SelectItem>
                          <SelectItem value="firmware_upgrade">
                            Firmware Upgrade - Show when firmware changes
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">When should this announcement be triggered?</p>
                    </div>

                    {/* Test UIDs */}
                    <div className="space-y-2 p-3 border border-dashed border-yellow-500/50 rounded-lg bg-yellow-500/5">
                      <Label className="flex items-center gap-2">
                        <span className="text-yellow-600">Test Mode</span>
                        {testUids && <Badge variant="outline" className="text-yellow-600 border-yellow-600">Active</Badge>}
                      </Label>
                      <Input
                        placeholder="e.g., uid1, uid2, uid3"
                        value={testUids}
                        onChange={(e) => setTestUids(e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">
                        Comma-separated Firebase UIDs. When set, only these users will see the announcement.
                        Remove all UIDs to release to everyone.
                      </p>
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>

            {/* Display Options Section */}
            <Accordion type="single" collapsible className="border rounded-lg">
              <AccordionItem value="display" className="border-0">
                <AccordionTrigger className="px-4 py-3 hover:no-underline">
                  <div className="flex items-center gap-2">
                    <Settings2 className="h-4 w-4" />
                    <span>Display Options</span>
                    {(priority !== 0 || startAt || displayExpiresAt || !dismissible || !showOnce) && (
                      <Badge variant="secondary" className="ml-2">Configured</Badge>
                    )}
                  </div>
                </AccordionTrigger>
                <AccordionContent className="px-4 pb-4">
                  <div className="space-y-4">
                    {/* Priority */}
                    <div className="space-y-2">
                      <Label>Priority</Label>
                      <Input
                        type="number"
                        placeholder="0"
                        value={priority || ''}
                        onChange={(e) => setPriority(parseInt(e.target.value) || 0)}
                      />
                      <p className="text-xs text-muted-foreground">Higher number = shown first (default: 0)</p>
                    </div>

                    {/* Time window */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label>Start At</Label>
                        <Input
                          type="datetime-local"
                          value={startAt}
                          onChange={(e) => setStartAt(e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">Don&apos;t show before this time</p>
                      </div>
                      <div className="space-y-2">
                        <Label>Display Expires At</Label>
                        <Input
                          type="datetime-local"
                          value={displayExpiresAt}
                          onChange={(e) => setDisplayExpiresAt(e.target.value)}
                        />
                        <p className="text-xs text-muted-foreground">Don&apos;t show after this time</p>
                      </div>
                    </div>

                    {/* Boolean options */}
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>Dismissible</Label>
                          <p className="text-xs text-muted-foreground">User can skip/close the announcement</p>
                        </div>
                        <Switch
                          checked={dismissible}
                          onCheckedChange={setDismissible}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>Show Once</Label>
                          <p className="text-xs text-muted-foreground">Only show once per user</p>
                        </div>
                        <Switch
                          checked={showOnce}
                          onCheckedChange={setShowOnce}
                        />
                      </div>
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>

            {/* Changelog Content */}
            {type === 'changelog' && (
              <div className="space-y-4 border rounded-lg p-4">
                <div className="space-y-2">
                  <Label>Changelog Title</Label>
                  <Input
                    placeholder="e.g., What's New in 1.0.522"
                    value={changelogTitle}
                    onChange={(e) => setChangelogTitle(e.target.value)}
                  />
                </div>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Label>Changes</Label>
                    <Button type="button" variant="outline" size="sm" onClick={addChange}>
                      <Plus className="h-4 w-4 mr-1" /> Add Change
                    </Button>
                  </div>
                  {changes.map((change, i) => (
                    <div key={i} className="space-y-2 p-3 border rounded-md relative">
                      {changes.length > 1 && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="absolute top-2 right-2 h-6 w-6"
                          onClick={() => removeChange(i)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      )}
                      <div className="grid grid-cols-[80px_1fr] gap-2">
                        <div>
                          <Label className="text-xs">Icon</Label>
                          <Input
                            placeholder="emoji"
                            value={change.icon || ''}
                            onChange={(e) => updateChange(i, 'icon', e.target.value)}
                            className="text-center text-lg"
                            maxLength={4}
                          />
                        </div>
                        <div>
                          <Label className="text-xs">Title</Label>
                          <Input
                            placeholder="Feature title"
                            value={change.title}
                            onChange={(e) => updateChange(i, 'title', e.target.value)}
                          />
                        </div>
                      </div>
                      <div>
                        <Label className="text-xs">Description</Label>
                        <Textarea
                          placeholder="Describe the change..."
                          value={change.description}
                          onChange={(e) => updateChange(i, 'description', e.target.value)}
                          rows={2}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Feature Content */}
            {type === 'feature' && (
              <div className="space-y-4 border rounded-lg p-4">
                <div className="space-y-2">
                  <Label>Feature Title</Label>
                  <Input
                    placeholder="e.g., We've updated how your Omi works"
                    value={featureTitle}
                    onChange={(e) => setFeatureTitle(e.target.value)}
                  />
                </div>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Label>Steps</Label>
                    <Button type="button" variant="outline" size="sm" onClick={addStep}>
                      <Plus className="h-4 w-4 mr-1" /> Add Step
                    </Button>
                  </div>
                  {steps.map((step, i) => (
                    <div key={i} className="space-y-2 p-3 border rounded-md relative">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">Step {i + 1}</span>
                        {steps.length > 1 && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={() => removeStep(i)}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                      <Input
                        placeholder="Step title"
                        value={step.title}
                        onChange={(e) => updateStep(i, 'title', e.target.value)}
                      />
                      <Textarea
                        placeholder="Step description..."
                        value={step.description}
                        onChange={(e) => updateStep(i, 'description', e.target.value)}
                        rows={2}
                      />
                      <ImageUpload
                        value={step.image_url || ''}
                        onChange={(url) => updateStep(i, 'image_url', url)}
                        onFileSelect={(file) => updateStepPendingFile(i, file)}
                        pendingFile={stepPendingFiles[i]}
                        label="Image (optional)"
                      />
                      <Input
                        placeholder="Highlight text (optional)"
                        value={step.highlight_text || ''}
                        onChange={(e) => updateStep(i, 'highlight_text', e.target.value)}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Announcement Content */}
            {type === 'announcement' && (
              <div className="space-y-4 border rounded-lg p-4">
                <div className="space-y-2">
                  <Label>Title</Label>
                  <Input
                    placeholder="e.g., Omi Premium is here!"
                    value={announcementTitle}
                    onChange={(e) => setAnnouncementTitle(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Body</Label>
                  <Textarea
                    placeholder="Announcement body text..."
                    value={announcementBody}
                    onChange={(e) => setAnnouncementBody(e.target.value)}
                    rows={3}
                  />
                </div>
                <ImageUpload
                  value={announcementImageUrl}
                  onChange={setAnnouncementImageUrl}
                  onFileSelect={setAnnouncementPendingFile}
                  pendingFile={announcementPendingFile}
                  label="Image (optional)"
                />
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>CTA Button Text</Label>
                    <Input
                      placeholder="e.g., Learn More"
                      value={ctaText}
                      onChange={(e) => setCtaText(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>CTA Action</Label>
                    <Input
                      placeholder="e.g., navigate:/settings/premium"
                      value={ctaAction}
                      onChange={(e) => setCtaAction(e.target.value)}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? 'Saving...' : editingAnnouncement ? 'Update' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function AnnouncementsPage() {
  const { announcements, isLoading, error, createAnnouncement, updateAnnouncement, deleteAnnouncement, toggleActive, mutate } = useAnnouncements();
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingAnnouncement, setEditingAnnouncement] = useState<Announcement | null>(null);
  const [typeFilter, setTypeFilter] = useState<AnnouncementType | 'all'>('all');

  const filteredAnnouncements = typeFilter === 'all'
    ? announcements
    : announcements.filter(a => a.type === typeFilter);

  const handleCreate = async (data: CreateAnnouncementData) => {
    try {
      await createAnnouncement(data);
      toast.success('Announcement created successfully');
    } catch (err: any) {
      toast.error(err?.message || 'Failed to create announcement');
      throw err;
    }
  };

  const handleUpdate = async (data: CreateAnnouncementData) => {
    if (!editingAnnouncement) return;
    try {
      await updateAnnouncement(editingAnnouncement.id, {
        ...data,
        content: data.content,
      });
      toast.success('Announcement updated successfully');
      setEditingAnnouncement(null);
    } catch (err: any) {
      toast.error(err?.message || 'Failed to update announcement');
      throw err;
    }
  };

  const handleToggleActive = async (id: string, active: boolean) => {
    try {
      await toggleActive(id, active);
      toast.success(active ? 'Announcement activated' : 'Announcement deactivated');
    } catch (err: any) {
      toast.error(err?.message || 'Failed to update announcement');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this announcement?')) return;
    try {
      await deleteAnnouncement(id, true);
      toast.success('Announcement deleted');
    } catch (err: any) {
      toast.error(err?.message || 'Failed to delete announcement');
    }
  };

  const handleEdit = (announcement: Announcement) => {
    setEditingAnnouncement(announcement);
    setIsDialogOpen(true);
  };

  const handleDialogOpenChange = (open: boolean) => {
    setIsDialogOpen(open);
    if (!open) {
      setEditingAnnouncement(null);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Announcements</h1>
          <p className="text-muted-foreground mt-1">
            Manage app updates, feature announcements, and promotions
          </p>
        </div>
        <Button onClick={() => setIsDialogOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Create Announcement
        </Button>
      </div>

      {/* Filter tabs */}
      <Tabs value={typeFilter} onValueChange={(v) => setTypeFilter(v as AnnouncementType | 'all')}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="changelog" className="gap-1">
            <FileText className="h-4 w-4" /> Changelogs
          </TabsTrigger>
          <TabsTrigger value="feature" className="gap-1">
            <Sparkles className="h-4 w-4" /> Features
          </TabsTrigger>
          <TabsTrigger value="announcement" className="gap-1">
            <Megaphone className="h-4 w-4" /> Announcements
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {isLoading ? (
        <div className="flex items-center justify-center min-h-[300px]">
          <Spinner />
        </div>
      ) : error ? (
        <p className="text-destructive text-center py-4">
          Error: {(error as any)?.message || 'Failed to load announcements'}
        </p>
      ) : filteredAnnouncements.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Megaphone className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>No announcements found</p>
          <Button variant="outline" className="mt-4" onClick={() => setIsDialogOpen(true)}>
            Create your first announcement
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredAnnouncements.map((announcement) => (
            <AnnouncementCard
              key={announcement.id}
              announcement={announcement}
              onToggleActive={handleToggleActive}
              onDelete={handleDelete}
              onEdit={handleEdit}
            />
          ))}
        </div>
      )}

      <AnnouncementFormDialog
        open={isDialogOpen}
        onOpenChange={handleDialogOpenChange}
        onSubmit={editingAnnouncement ? handleUpdate : handleCreate}
        editingAnnouncement={editingAnnouncement}
      />
    </div>
  );
}
