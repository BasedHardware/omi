'use client';

import { OmiAppDetailedData } from '@/hooks/useAppDetails';
import { useAppDetails } from '@/hooks/useAppDetails';
// import { OmiAppCapability } from '@/lib/services/omi-api/types'; // Not strictly needed if capabilities are strings
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
  SheetClose,
} from "@/components/ui/sheet"; // Assuming you have shadcn/ui Sheet
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Cpu, 
    MessageCircle, 
    Bell, 
    Puzzle, 
    User 
} from 'lucide-react'; // Icons for capabilities

interface AppDetailViewProps {
  appDetails?: OmiAppDetailedData | null;
  isOpen: boolean;
  onClose: () => void;
  appName?: string; // Optional: pass appName for a better title if details are loading
  appId?: string; // Optional: pass appId to fetch details if appDetails is null
}

// Helper to format date strings (if you have date fields)
const formatDate = (dateString: string | undefined) => {
  if (!dateString) return 'N/A';
  try {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric', month: 'long', day: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  } catch (e) {
    return dateString; // Return original if not a valid date
  }
};

// Capability Icons Helper
const getCapabilityIcon = (capability: string) => { // capability is a string
  switch (capability) {
    case 'memories':
      return <Cpu className="h-5 w-5 mr-2" />;
    case 'chat':
      return <MessageCircle className="h-5 w-5 mr-2" />;
    case 'proactive_notification':
      return <Bell className="h-5 w-5 mr-2" />;
    case 'external_integration':
      return <Puzzle className="h-5 w-5 mr-2" />;
    case 'persona':
      return <User className="h-5 w-5 mr-2" />;
    default:
      return null;
  }
};

export function AppDetailView({ appDetails: propAppDetails, isOpen, onClose, appName, appId }: AppDetailViewProps) {
  // Use the hook to fetch details if appDetails is not provided
  const { appDetails: fetchedAppDetails, isLoadingDetails, errorDetails } = useAppDetails(appId || null);
  
  // Use provided appDetails if available, otherwise use fetched details
  const appDetails = propAppDetails || fetchedAppDetails;

  if (!isOpen) return null;

  const commonExcludedKeys = ['id', 'name', 'author_name', 'author', 'version', 'status', 'approved', 'short_description', 'long_description', 'created_at', 'updated_at', 'image', 'email', 'capabilities', 'external_integration_details', 'developer_contact'];

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="sm:max-w-2xl w-full flex flex-col">
        <SheetHeader className="pr-6">
          <div className="flex items-start space-x-4">
            {appDetails?.image && (
              <img 
                src={appDetails.image} 
                alt={appDetails.name || appName || 'App Image'} 
                className="w-16 h-16 rounded-lg object-cover border flex-shrink-0"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            )}
            <div className="flex-grow">
              <SheetTitle className="text-2xl">{appDetails?.name || appName || 'Loading...'}</SheetTitle>
              {appDetails?.short_description && 
                <SheetDescription className="mt-1">{appDetails.short_description}</SheetDescription>
              }
            </div>
          </div>
        </SheetHeader>
        <ScrollArea className="flex-grow pr-6 -mr-6">
          {isLoadingDetails ? (
            <div className="py-4 text-center text-muted-foreground">Loading details...</div>
          ) : errorDetails ? (
            <div className="py-4 text-center text-destructive">Error loading details: {errorDetails.message}</div>
          ) : appDetails ? (
            <div className="space-y-6 py-4">
              <DetailSection title="General Information">
                <DetailItem label="App ID" value={appDetails.id} />
                {appDetails.developer_contact?.email && <DetailItem label="Developer Email" value={appDetails.developer_contact.email} />}
                {!appDetails.developer_contact?.email && appDetails.email && <DetailItem label="Contact Email" value={appDetails.email} />}
                <DetailItem label="Author" value={appDetails.author_name || appDetails.author} />
                <DetailItem label="Version" value={appDetails.version} />
                <DetailItem label="Status" value={<Badge variant={appDetails.status === 'approved' ? 'default' : 'outline'} className="capitalize">{appDetails.status?.replace("-", " ") || 'N/A'}</Badge>} />
                <DetailItem label="Approved" value={appDetails.approved ? <Badge variant="default">Yes</Badge> : <Badge variant="secondary">No</Badge>} />
              </DetailSection>

              {appDetails.long_description && (
                <DetailSection title="Full Description">
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                    {appDetails.long_description}
                  </p>
                </DetailSection>
              )}

              {appDetails.capabilities && Array.isArray(appDetails.capabilities) && appDetails.capabilities.length > 0 && (
                <DetailSection title="Capabilities">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {appDetails.capabilities.map((capability: string) => ( // Treat as string array
                      <div key={capability} className="flex items-center p-2 bg-background rounded-md border">
                        {getCapabilityIcon(capability)}
                        <span className="capitalize text-sm">
                          {capability.replace(/_/g, ' ')}
                        </span>
                      </div>
                    ))}
                  </div>
                </DetailSection>
              )}

              {(appDetails.external_integration_details || appDetails.external_integration) && (
                <DetailSection title="External Integration">
                  <pre className="text-xs bg-background p-2 rounded-md border overflow-x-auto">
                    {JSON.stringify(appDetails.external_integration_details || appDetails.external_integration, null, 2)}
                  </pre>
                </DetailSection>
              )}

              <DetailSection title="Timestamps">
                <DetailItem label="Created At" value={formatDate(appDetails.created_at?._seconds ? new Date(appDetails.created_at._seconds * 1000).toISOString() : appDetails.created_at)} />
                <DetailItem label="Updated At" value={formatDate(appDetails.updated_at?._seconds ? new Date(appDetails.updated_at._seconds * 1000).toISOString() : appDetails.updated_at)} />
              </DetailSection>
              
              <DetailSection title="Other Data">
                {Object.entries(appDetails)
                  .filter(([key]) => !commonExcludedKeys.includes(key) && appDetails[key] !== undefined && appDetails[key] !== null)
                  .map(([key, value]) => (
                    <DetailItem 
                        key={key} 
                        label={key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())} 
                        value={typeof value === 'object' ? <pre className="text-xs text-left whitespace-pre-wrap">{JSON.stringify(value, null, 2)}</pre> : String(value)} 
                    />
                  ))}
                 {Object.entries(appDetails).filter(([key]) => !commonExcludedKeys.includes(key) && appDetails[key] !== undefined && appDetails[key] !== null).length === 0 && (
                    <p className="text-sm text-muted-foreground">No other data available.</p>
                 )}
              </DetailSection>

            </div>
          ) : (
            <div className="py-4 text-center text-muted-foreground">No app details available.</div>
          )}
        </ScrollArea>
        <SheetFooter className="mt-auto pt-4 pr-6 -mr-6">
          <SheetClose asChild>
            <Button type="button" variant="outline">Close</Button>
          </SheetClose>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

const DetailSection: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div>
    <h3 className="text-md font-semibold mb-2 text-primary">{title}</h3>
    <div className="space-y-1.5 text-sm border p-3 rounded-md bg-muted/30">
      {children}
    </div>
  </div>
);

const DetailItem: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex justify-between">
    <span className="text-muted-foreground">{label}:</span>
    <span className="text-right font-medium">{value || 'N/A'}</span>
  </div>
); 