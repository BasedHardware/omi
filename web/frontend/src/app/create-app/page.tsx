'use client';

import { useAuth } from '../../hooks/useAuth';
import { useEffect, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import {
  getAppInitializationData,
  generateDescription as generateDescriptionAction,
  uploadThumbnails,
  submitApp,
  type Category,
  type TriggerEvent,
  type NotificationScope,
  type AppCapability,
  type PaymentPlan,
  type AppSubmissionData,
  type ExternalIntegration,
  type ProactiveNotification
} from '../../actions/apps';
import LoadingState from '@/src/components/loading-state';

export default function CreateAppPage() {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();
  const submissionRef = useRef(false); // Add ref to track submission attempts

  // Loading states
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showSubmitDialog, setShowSubmitDialog] = useState(false);
  const [showSubmitAppConfirmation, setShowSubmitAppConfirmation] = useState(true);
  const [isGeneratingDescription, setIsGeneratingDescription] = useState(false);
  const [isUploadingThumbnail, setIsUploadingThumbnail] = useState(false);
  const [submissionStarted, setSubmissionStarted] = useState(false);
  const [isRedirecting, setIsRedirecting] = useState(false); // New state for post-submission loading

  // Data
  const [categories, setCategories] = useState<Category[]>([]);
  const [capabilities, setCapabilities] = useState<AppCapability[]>([]);
  const [paymentPlans, setPaymentPlans] = useState<PaymentPlan[]>([]);
  
  // Form state
  const [appName, setAppName] = useState('');
  const [appDescription, setAppDescription] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedCapabilities, setSelectedCapabilities] = useState<AppCapability[]>([]);
  const [isPaid, setIsPaid] = useState(false);
  const [price, setPrice] = useState('');
  const [selectedPaymentPlan, setSelectedPaymentPlan] = useState<string>('');
  const [makeAppPublic, setMakeAppPublic] = useState(false);
  const [termsAgreed, setTermsAgreed] = useState(false);
  
  // Prompts
  const [chatPrompt, setChatPrompt] = useState('');
  const [conversationPrompt, setConversationPrompt] = useState('');
  
  // External Integration
  const [triggerEvent, setTriggerEvent] = useState<string>('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [setupCompletedUrl, setSetupCompletedUrl] = useState('');
  const [instructions, setInstructions] = useState('');
  const [authUrl, setAuthUrl] = useState('');
  const [appHomeUrl, setAppHomeUrl] = useState('');
  
  // Notification scopes
  const [selectedScopes, setSelectedScopes] = useState<NotificationScope[]>([]);
  
  // Image and thumbnails
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string>('');
  const [thumbnailUrls, setThumbnailUrls] = useState<string[]>([]);
  
  // Validation
  const [isValid, setIsValid] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      console.log('[CreateAppPage] User not authenticated, redirecting to / ');
      router.push('/');
    }
  }, [user, loading, router]);

  useEffect(() => {
    if (user) {
      console.log('[CreateAppPage] User authenticated, initializing data...');
      initializeData();
    }
  }, [user]);

  const initializeData = async () => {
    setIsLoading(true);
    console.log('🚀 [initializeData] Starting data initialization...');
    
    try {
      const token = await user?.getIdToken();
      console.log('📋 [initializeData] Fetching app initialization data...');
      
      const data = await getAppInitializationData(token);
      
      setCategories(data.categories);
      setCapabilities(data.capabilities);
      setPaymentPlans(data.paymentPlans);
      
      console.log('✅ [initializeData] Data initialization complete');
    } catch (error) {
      console.error('❌ [initializeData] Error fetching data:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImageFile(file);
      const reader = new FileReader();
      reader.onload = (event) => {
        setImagePreview(event.target?.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const processImageFile = (file: File) => {
    // Validate file size (10MB limit)
    const maxSize = 10 * 1024 * 1024; // 10MB in bytes
    if (file.size > maxSize) {
      alert('File size must be less than 10MB');
      return;
    }

    // Validate file type
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
      alert('Please upload a valid image file (PNG, JPG, JPEG, WEBP)');
      return;
    }

    setIsUploadingThumbnail(true);
    const reader = new FileReader();
    reader.onload = (event) => {
      const result = event.target?.result as string;
      setThumbnailUrls(prev => [...prev, result]);
      setIsUploadingThumbnail(false);
    };
    reader.onerror = () => {
      alert('Error reading file. Please try again.');
      setIsUploadingThumbnail(false);
    };
    reader.readAsDataURL(file);
  };

  const handleThumbnailUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processImageFile(file);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (thumbnailUrls.length >= 5) {
      alert('Maximum 5 images allowed');
      return;
    }
    
    const files = Array.from(e.dataTransfer.files);
    const imageFile = files.find(file => file.type.startsWith('image/'));
    
    if (imageFile) {
      processImageFile(imageFile);
    } else {
      alert('Please drop an image file');
    }
  };

  const removeThumbnail = (index: number) => {
    setThumbnailUrls(prev => prev.filter((_, i) => i !== index));
  };

  const toggleCapability = (capability: AppCapability) => {
    setSelectedCapabilities(prev => {
      const isSelected = prev.some(c => c.id === capability.id);
      if (isSelected) {
        return prev.filter(c => c.id !== capability.id);
      } else {
        if (prev.length === 1 && prev[0].id === 'persona') {
          return prev; // Can't add other capabilities with persona
        } else if (capability.id === 'persona' && prev.length > 0) {
          return prev; // Can't add persona with other capabilities
        } else {
          return [...prev, capability];
        }
      }
    });
  };

  const toggleScope = (scope: NotificationScope) => {
    setSelectedScopes(prev => {
      const isSelected = prev.some(s => s.id === scope.id);
      if (isSelected) {
        return prev.filter(s => s.id !== scope.id);
      } else {
        return [...prev, scope];
      }
    });
  };

  const isCapabilitySelected = (capability: AppCapability) => {
    return selectedCapabilities.some(c => c.id === capability.id);
  };

  const isCapabilitySelectedById = useCallback((id: string) => {
    return selectedCapabilities.some(c => c.id === id);
  }, [selectedCapabilities]);

  const isScopeSelected = (scope: NotificationScope) => {
    return selectedScopes.some(s => s.id === scope.id);
  };

  const getTriggerEvents = (): TriggerEvent[] => {
    const externalIntegrationCapability = selectedCapabilities.find(c => c.id === 'external_integration');
    return externalIntegrationCapability?.triggers || [];
  };

  const getNotificationScopes = (): NotificationScope[] => {
    const notificationCapability = selectedCapabilities.find(c => c.id === 'proactive_notification');
    return notificationCapability?.scopes || [];
  };

  const generateDescription = async () => {
    if (!appName || !appDescription) return;
    
    setIsGeneratingDescription(true);
    try {
      const token = await user?.getIdToken();
      if (!token) {
        console.error('[generateDescription] No token available');
        return;
      }
      
      const result = await generateDescriptionAction({
        name: appName,
        description: appDescription
      }, token);
      
      if (result) {
        setAppDescription(result.description);
      } else {
        console.error('[generateDescription] Failed to generate description');
      }
    } catch (error) {
      console.error('[generateDescription] Error:', error);
    } finally {
      setIsGeneratingDescription(false);
    }
  };

  const validateForm = useCallback(() => {
    const isFormValid = (
      appName.trim() !== '' &&
      appDescription.trim() !== '' &&
      selectedCategory !== '' &&
      selectedCapabilities.length > 0 &&
      (imageFile !== null || imagePreview !== '') &&
      termsAgreed &&
      (!isPaid || (price !== '' && selectedPaymentPlan !== '')) &&
      (!isCapabilitySelectedById('chat') || chatPrompt.trim() !== '') &&
      (!isCapabilitySelectedById('memories') || conversationPrompt.trim() !== '') &&
      (!isCapabilitySelectedById('external_integration') || (triggerEvent !== '' && webhookUrl.trim() !== '')) &&
      (!isCapabilitySelectedById('proactive_notification') || selectedScopes.length > 0)
    );
    return Boolean(isFormValid);
  }, [appName, appDescription, selectedCategory, selectedCapabilities, imageFile, imagePreview, termsAgreed, isPaid, price, selectedPaymentPlan, chatPrompt, conversationPrompt, triggerEvent, webhookUrl, selectedScopes, isCapabilitySelectedById]);

  useEffect(() => {
    setIsValid(validateForm());
  }, [validateForm]);

  const handleSubmit = async () => {
    console.log('🔵 [handleSubmit] Attempting submission. Current guard states:', { 
      isValid: validateForm(), 
      hasUser: !!user, 
      isSubmitting, 
      submissionStarted, 
      submissionRefCurrent: submissionRef.current 
    });

    if (!validateForm() || !user || isSubmitting || submissionStarted || submissionRef.current) {
      console.warn('⚠️ [handleSubmit] Submission blocked by initial guard.');
      return;
    }
    
    submissionRef.current = true;
    setIsSubmitting(true);
    setSubmissionStarted(true);
    console.log('🟢 [handleSubmit] Submission initiated, guards set.');
    
    try {
      const token = await user.getIdToken();
      if (!token) {
        console.error('❌ [handleSubmit] No authentication token available');
        throw new Error('No authentication token available');
      }
      console.log('🔑 [handleSubmit] Token acquired.');

      const appData: AppSubmissionData = {
        name: appName.trim(),
        description: appDescription.trim(),
        capabilities: selectedCapabilities.map((e) => e.id),
        deleted: false,
        uid: user.uid,
        category: selectedCategory,
        private: !makeAppPublic,
        is_paid: isPaid,
        price: isPaid && price ? parseFloat(price) : 0.0,
        payment_plan: selectedPaymentPlan || null,
        thumbnails: [] as string[],
      };

      for (const capability of selectedCapabilities) {
        if (capability.id === 'external_integration') {
          const externalIntegration: ExternalIntegration = {
            triggers_on: triggerEvent,
            webhook_url: webhookUrl.trim(),
            setup_completed_url: setupCompletedUrl.trim(),
            setup_instructions_file_path: instructions.trim(),
            app_home_url: appHomeUrl.trim(),
            auth_steps: [],
          };
          if (authUrl.trim()) {
            externalIntegration.auth_steps = [{
              url: authUrl.trim(),
              name: `Setup ${appName}`,
            }];
          }
          appData.external_integration = externalIntegration;
        }
        if (capability.id === 'chat') appData.chat_prompt = chatPrompt.trim();
        if (capability.id === 'memories') appData.memory_prompt = conversationPrompt.trim();
        if (capability.id === 'proactive_notification') {
          const proactiveNotification: ProactiveNotification = { 
            scopes: selectedScopes.map((s) => s.id) 
          };
          appData.proactive_notification = proactiveNotification;
        }
      }
      console.log('📝 [handleSubmit] App data constructed:', appData);

      const thumbnailIds = await uploadThumbnails(thumbnailUrls, token);
      appData.thumbnails = thumbnailIds;

      // Create FormData for the submission
      const submissionFormData = new FormData();
      submissionFormData.append('app_data', JSON.stringify(appData));
      submissionFormData.append('token', token);

      // Handle app icon
      if (imageFile) {
        submissionFormData.append('file', imageFile);
        console.log('🖼️ [handleSubmit] App icon (user-provided) prepared.');
      } else {
        console.log('🖼️ [handleSubmit] No user-provided app icon, generating default...');
        const blob = await new Promise<Blob | null>((resolve) => {
          const canvas = document.createElement('canvas');
          canvas.width = 100;
          canvas.height = 100;
          const ctx = canvas.getContext('2d');
          if (ctx) {
            ctx.fillStyle = '#6C2BD9';
            ctx.fillRect(0, 0, 100, 100);
            ctx.fillStyle = 'white';
            ctx.font = '48px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(appName.charAt(0).toUpperCase() || 'A', 50, 65);
            canvas.toBlob(resolve, 'image/png');
          } else {
            console.error('❌ [handleSubmit] Failed to get canvas context for default icon.');
            resolve(null);
          }
        });
        if (blob) {
          submissionFormData.append('file', blob, 'default-icon.png');
          console.log('🖼️ [handleSubmit] Default app icon generated.');
        } else {
          console.warn('⚠️ [handleSubmit] Failed to generate default icon blob.');
        }
      }

      console.log('🚀 [handleSubmit] Submitting app to backend.');
      const result = await submitApp(submissionFormData);

      console.log('✅ [handleSubmit] App submission successful:', result);

      alert(`App "${appName}" submitted successfully! ${makeAppPublic ? 'Your app will be reviewed and made public.' : 'Your app will be reviewed and made available to you privately.'} You can start using it immediately, even during the review!`);
      
      setIsRedirecting(true);
      console.log('↪️ [handleSubmit] App submitted, preparing to redirect to /');
      setTimeout(() => {
        router.push('/');
      }, 1500);
      
    } catch (error: any) {
      console.error('❌ [handleSubmit] App submission failed with error:', error.message, error.stack);
      submissionRef.current = false;
      setSubmissionStarted(false);
      setIsRedirecting(false);
      console.log('🔄 [handleSubmit] Guards reset due to error.');
      
      let errorMessage = 'Error submitting app. Please try again.';
      if (error.message.includes('422')) errorMessage = 'Please check all required fields and try again.';
      else if (error.message.includes('401')) errorMessage = 'Authentication failed. Please sign in again.';
      else if (error.message.includes('name')) errorMessage = 'App name is required.';
      else if (error.message.includes('description')) errorMessage = 'App description is required.';
      else if (error.message.includes('category')) errorMessage = 'Please select a category for your app.';
      else if (error.message.includes('capabilities')) errorMessage = 'Please select at least one capability for your app.';
      alert(errorMessage);
    } finally {
      setIsSubmitting(false);
      console.log('🏁 [handleSubmit] Submission flow ended. isSubmitting set to false.');
    }
  };

  if (!user) {
    return null;
  }

  if (isLoading || (isSubmitting && submissionRef.current) || isRedirecting) {
    return <LoadingState isRedirecting={isRedirecting} isSubmitting={isSubmitting} />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-[#0B0F17] to-gray-800 pt-16">
      {/* Header - Adjusted top-16 for potential global app bar */}
      <div className="fixed top-16 left-0 right-0 z-40 bg-[#0B0F17]/80 backdrop-blur-md border-b border-white/10">
        <div className="mx-auto max-w-3xl px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-6">
              <button
                onClick={() => router.back()}
                className="group flex items-center space-x-2 text-gray-400 hover:text-white transition-colors"
              >
                <svg className="h-5 w-5 transition-transform group-hover:-translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                <span>Back</span>
              </button>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">
                  Create App
                </h1>
                <p className="text-sm text-gray-400">Build and deploy your custom AI application</p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-3">
                <div className="h-8 w-8 rounded-full bg-gradient-to-r from-blue-500 to-purple-600 flex items-center justify-center text-sm font-medium text-white">
                  {user.displayName?.charAt(0) || user.email?.charAt(0) || 'U'}
                </div>
                <span className="text-sm text-gray-300 hidden sm:block">
                  {user.displayName || user.email}
                </span>
            </div>
            <button
                onClick={signOut}
                className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              Sign Out
            </button>
            </div>
          </div>
          </div>
        </div>

      {/* Main Content - Adjusted for single column layout and top padding for fixed header */}
      <div className="mx-auto max-w-3xl px-6 py-8 flex flex-col space-y-8 mt-16">
        {/* Help Section */}
        <div className="mt-4">
          <div
            onClick={() => window.open('https://omi.me/apps/introduction', '_blank')}
            className="cursor-pointer group"
          >
            <div className="rounded-[0.5rem] bg-gradient-to-r from-blue-600/10 to-purple-600/10 border border-blue-500/20 p-6 transition-all hover:from-blue-600/20 hover:to-purple-600/20 hover:border-blue-500/40">
              <div className="flex items-center justify-center space-x-3">
                <svg className="h-6 w-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <p className="text-white font-medium">
                  New to app building? <span className="text-blue-400 group-hover:text-blue-300">Click here to get started!</span>
                </p>
                <svg className="h-5 w-5 text-gray-400 transition-transform group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </div>
            </div>
          </div>
        </div>

        {/* App Basic Information */}
        <div className="bg-white/5 backdrop-blur-sm rounded-[0.5rem] border border-white/10 p-8">
          <div className="flex items-center space-x-3 mb-6">
            <div className="h-10 w-10 rounded-[0.5rem] bg-gradient-to-r from-blue-500 to-purple-600 flex items-center justify-center">
              <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h3 className="text-xl font-semibold text-white">App Information</h3>
              <p className="text-sm text-gray-400">Basic details about your application</p>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-300 mb-3">App Icon</label>
              <div className="flex items-center space-x-6">
                {imagePreview ? (
                  <div className="relative h-20 w-20 overflow-hidden rounded-[0.5rem] border-2 border-white/20">
                    <Image
                      src={imagePreview}
                      alt="App icon preview"
                      fill
                      className="object-cover"
                    />
                  </div>
                ) : (
                  <div className="flex h-20 w-20 items-center justify-center rounded-[0.5rem] bg-gradient-to-br from-gray-700 to-gray-800 border-2 border-dashed border-gray-600">
                    <svg className="h-8 w-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  </div>
                )}
                <label className="cursor-pointer rounded-[0.5rem] bg-gradient-to-r from-blue-600 to-purple-600 px-6 py-3 text-sm font-medium text-white hover:from-blue-700 hover:to-purple-700 transition-all">
                  Choose Image
                  <input type="file" accept="image/*" onChange={handleImageUpload} className="hidden" />
                </label>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-3">App Name <span className="text-red-400">*</span></label>
              <input
                type="text"
                value={appName}
                onChange={(e) => setAppName(e.target.value)}
                placeholder="Enter app name"
                className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-3">Category <span className="text-red-400">*</span></label>
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all appearance-none pr-8"
              >
                <option value="" className="bg-gray-800">Select a category</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id} className="bg-gray-800">{category.title}</option>
                ))}
              </select>
            </div>

            <div className="md:col-span-2">
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm font-medium text-gray-300">App Description <span className="text-red-400">*</span></label>
                <button
                  onClick={generateDescription}
                  disabled={isGeneratingDescription || !appName || !appDescription}
                  className="rounded-[0.5rem] bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-2 text-xs font-medium text-white hover:from-emerald-700 hover:to-teal-700 disabled:from-gray-600 disabled:to-gray-600 disabled:cursor-not-allowed transition-all flex items-center space-x-2"
                >
                  {isGeneratingDescription ? (
                    <div className="flex items-center space-x-2">
                      <div className="h-3 w-3 animate-spin rounded-full border border-white/40 border-t-white"></div>
                      <span>Generating...</span>
                    </div>
                  ) : (
                    <>
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      <span>Enhance Description</span>
                    </>
                  )}
                </button>
              </div>
              <textarea
                value={appDescription}
                onChange={(e) => setAppDescription(e.target.value)}
                placeholder="Describe what your app does and how it helps users..."
                rows={4}
                className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all resize-none"
              />
            </div>
          </div>
        </div>

        {/* Pricing Section */}
        <div className="bg-white/5 backdrop-blur-sm rounded-[0.5rem] border border-white/10 p-8">
          <div className="flex items-center space-x-3 mb-6">
            <div className="h-10 w-10 rounded-[0.5rem] bg-gradient-to-r from-emerald-500 to-teal-600 flex items-center justify-center">
              <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1" />
              </svg>
            </div>
            <div>
              <h3 className="text-xl font-semibold text-white">Pricing Model</h3>
              <p className="text-sm text-gray-400">Choose how you want to monetize your app</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div className={`relative rounded-[0.5rem] border-2 p-6 cursor-pointer transition-all ${ 
              !isPaid ? 'border-blue-500 bg-blue-500/10' : 'border-white/20 bg-white/5 hover:border-white/30'
            }`} onClick={() => {
              setIsPaid(false);
              setSelectedPaymentPlan('');
              setPrice('');
            }}>
              <div className="flex items-center space-x-3">
                <div className={`h-5 w-5 rounded-full border-2 flex items-center justify-center ${ 
                  !isPaid ? 'border-blue-500 bg-blue-500' : 'border-gray-400'
                }`}>
                  {!isPaid && <div className="h-2 w-2 rounded-full bg-white"></div>}
                </div>
                <div>
                  <h4 className="font-semibold text-white">Free</h4>
                  <p className="text-sm text-gray-400">No cost for users</p>
                </div>
              </div>
            </div>

            {paymentPlans.length > 0 && (
              <div className={`relative rounded-[0.5rem] border-2 p-6 cursor-pointer transition-all ${ 
                isPaid ? 'border-emerald-500 bg-emerald-500/10' : 'border-white/20 bg-white/5 hover:border-white/30'
              }`} onClick={() => {
                  setIsPaid(true);
                  if (paymentPlans.length > 0) {
                    const monthlyPlan = paymentPlans.find(p => p.title.toLowerCase().includes('monthly'));
                    setSelectedPaymentPlan(monthlyPlan ? monthlyPlan.id : paymentPlans[0].id);
                  } else {
                    setSelectedPaymentPlan(''); 
                  }
              }}>
                <div className="flex items-center space-x-3">
                  <div className={`h-5 w-5 rounded-full border-2 flex items-center justify-center ${ 
                    isPaid ? 'border-emerald-500 bg-emerald-500' : 'border-gray-400'
                  }`}>
                     {isPaid && <div className="h-2 w-2 rounded-full bg-white"></div>}
                  </div>
                  <div>
                    <h4 className="font-semibold text-white">Paid</h4>
                    <p className="text-sm text-gray-400">Charge users for access</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {isPaid && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-6 border-t border-white/10">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">Price (USD) <span className="text-red-400">*</span></label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400">$</span>
                  <input
                    type="number"
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                    placeholder="0.00"
                    min="0"
                    step="0.01"
                    className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 pl-8 pr-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">Payment Plan <span className="text-red-400">*</span></label>
                <select
                  value={selectedPaymentPlan}
                  onChange={(e) => setSelectedPaymentPlan(e.target.value)}
                  className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                >
                  <option value="" className="bg-gray-800">Select payment plan</option>
                  {paymentPlans.map((plan) => (
                    <option key={plan.id} value={plan.id} className="bg-gray-800">{plan.title}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>
        
        {/* Preview and Screenshots */}
        <div className="bg-white/5 backdrop-blur-sm rounded-[0.5rem] border border-white/10 p-8">
            <div className="flex items-center space-x-3 mb-6">
                <div className="h-10 w-10 rounded-[0.5rem] bg-gradient-to-r from-pink-500 to-rose-500 flex items-center justify-center">
                    <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                </div>
                <div>
                    <h3 className="text-xl font-semibold text-white">Preview & Screenshots</h3>
                    <p className="text-sm text-gray-400">Add images to showcase your app (up to 5 images)</p>
                </div>
            </div>
            
            {/* Thumbnail Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {thumbnailUrls.map((url, index) => (
                <div key={index} className="group relative">
                  {/* Aspect Ratio Container - Made taller */}
                  <div className="relative aspect-[3/4] overflow-hidden rounded-[0.5rem] border border-white/20 bg-gray-800/50">
                    <Image
                      src={url}
                      alt={`Screenshot ${index + 1}`}
                      fill
                      className="object-cover transition-transform duration-300 group-hover:scale-105"
                      sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, (max-width: 1280px) 33vw, 25vw"
                    />
                    
                    {/* Overlay */}
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors duration-300" />
                    
                    {/* Delete Button */}
                    <button
                      onClick={() => removeThumbnail(index)}
                      className="absolute top-2 right-2 bg-red-500/80 hover:bg-red-500 text-white rounded-full p-1.5 opacity-0 group-hover:opacity-100 transition-all duration-300 transform translate-y-1 group-hover:translate-y-0"
                      title="Remove image"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                    
                    {/* Image Number Badge */}
                    <div className="absolute bottom-2 left-2 bg-black/60 text-white text-xs px-2 py-1 rounded-full">
                      {index + 1}
                    </div>
                  </div>
                </div>
              ))}
              
              {/* Add New Thumbnail Button */}
              {thumbnailUrls.length > 0 && thumbnailUrls.length < 5 && (
                <div className="group relative">
                  <label 
                    className={`relative aspect-[3/4] flex flex-col items-center justify-center rounded-[0.5rem] border-2 border-dashed border-gray-600 hover:border-gray-500 bg-gray-800/20 hover:bg-gray-800/40 transition-all duration-300 cursor-pointer p-6 ${
                      isUploadingThumbnail ? 'opacity-50 cursor-default' : ''
                    }`}
                    onDragOver={handleDragOver}
                    onDragEnter={handleDragEnter}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                  >
                    {isUploadingThumbnail ? (
                      <div className="flex flex-col items-center space-y-3">
                        <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-600 border-t-blue-500"></div>
                        <span className="text-sm text-gray-400">Uploading...</span>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center space-y-3 text-gray-400 group-hover:text-gray-300 transition-colors">
                        <div className="h-12 w-12 rounded-full bg-gray-700 group-hover:bg-gray-600 flex items-center justify-center transition-colors">
                          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                          </svg>
                        </div>
                        <div className="text-center">
                          <span className="text-sm font-medium">Add Image</span>
                          <p className="text-xs mt-1">Click or drag & drop</p>
                          <p className="text-xs text-gray-500">PNG, JPG up to 10MB</p>
                        </div>
                      </div>
                    )}
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleThumbnailUpload}
                      className="hidden"
                      disabled={isUploadingThumbnail}
                    />
                  </label>
                </div>
              )}
            </div>
            
            {/* Helper Text - Clean Empty State */}
            {thumbnailUrls.length === 0 && (
              <div className="py-12 px-8 text-center">
                <div className="h-16 w-16 mx-auto mb-6 rounded-full bg-gradient-to-r from-gray-700 to-gray-800 flex items-center justify-center">
                  <svg className="h-8 w-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
                <h4 className="text-lg font-medium text-white mb-3">No screenshots added yet</h4>
                <p className="text-gray-400 text-sm max-w-md mx-auto mb-6 leading-relaxed">
                  Add screenshots to showcase your app's features and functionality. High-quality images help users understand what your app does.
                </p>
                <label className="inline-flex items-center justify-center space-x-2 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white font-medium py-3 px-6 rounded-[0.375rem] transition-all duration-200 cursor-pointer">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                  <span>Add Screenshot</span>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleThumbnailUpload}
                    className="hidden"
                    disabled={isUploadingThumbnail}
                  />
                </label>
              </div>
            )}
        </div>

        {/* App Capabilities */}
        <div className="bg-white/5 backdrop-blur-sm rounded-[0.5rem] border border-white/10 p-8">
            <div className="flex items-center space-x-3 mb-6">
                <div className="h-10 w-10 rounded-[0.5rem] bg-gradient-to-r from-cyan-500 to-sky-600 flex items-center justify-center">
                    <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" /></svg>
                </div>
                <div>
                    <h3 className="text-xl font-semibold text-white">App Capabilities</h3>
                    <p className="text-sm text-gray-400">Select features for your app</p>
                </div>
            </div>
          <div className="flex flex-wrap gap-3">
            {capabilities.map((capability) => (
              <button
                key={capability.id}
                onClick={() => toggleCapability(capability)}
                className={`rounded-[0.5rem] px-4 py-2 text-sm font-medium transition-colors ${ 
                  isCapabilitySelected(capability)
                    ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-md' 
                    : 'bg-white/10 text-gray-300 hover:bg-white/20'
                }`}
              >
                {capability.title}
                {isCapabilitySelected(capability) && <span className="ml-1">✓</span>}
              </button>
            ))}
          </div>
        </div>

        {/* Prompt Fields */}
        {(isCapabilitySelectedById('chat') || isCapabilitySelectedById('memories')) && (
          <div className="bg-white/5 backdrop-blur-sm rounded-[0.5rem] border border-white/10 p-8">
            <div className="flex items-center space-x-3 mb-6">
                <div className="h-10 w-10 rounded-[0.5rem] bg-gradient-to-r from-orange-500 to-amber-500 flex items-center justify-center">
                     <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
                </div>
                <div>
                    <h3 className="text-xl font-semibold text-white">AI Prompts</h3>
                    <p className="text-sm text-gray-400">Configure AI behavior</p>
                </div>
            </div>
            
            {isCapabilitySelectedById('chat') && (
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-300 mb-2">Chat Prompt <span className="text-red-400">*</span></label>
                <textarea
                  value={chatPrompt}
                  onChange={(e) => setChatPrompt(e.target.value)}
                  placeholder="You are an awesome app, your job is to respond to the user queries..."
                  rows={3}
                  className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent transition-all resize-none"
                />
              </div>
            )}

            {isCapabilitySelectedById('memories') && (
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Conversation Prompt <span className="text-red-400">*</span></label>
                <textarea
                  value={conversationPrompt}
                  onChange={(e) => setConversationPrompt(e.target.value)}
                  placeholder="You are an awesome app, you will be given transcript and summary..."
                  rows={3}
                  className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent transition-all resize-none"
                />
              </div>
            )}
          </div>
        )}

        {/* External Integration */}
        {isCapabilitySelectedById('external_integration') && (
          <div className="bg-white/5 backdrop-blur-sm rounded-[0.5rem] border border-white/10 p-8">
             <div className="flex items-center space-x-3 mb-6">
                <div className="h-10 w-10 rounded-[0.5rem] bg-gradient-to-r from-lime-500 to-green-600 flex items-center justify-center">
                    <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
                </div>
                <div>
                    <h3 className="text-xl font-semibold text-white">External Integration</h3>
                    <p className="text-sm text-gray-400">Connect to other services</p>
                </div>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Trigger Event <span className="text-red-400">*</span></label>
                <select
                  value={triggerEvent}
                  onChange={(e) => setTriggerEvent(e.target.value)}
                  className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent transition-all"
                >
                  <option value="" className="bg-gray-800">Select trigger event</option>
                  {getTriggerEvents().map((event) => (
                    <option key={event.id} value={event.id} className="bg-gray-800">{event.title}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Webhook URL <span className="text-red-400">*</span></label>
                <input type="url" value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} placeholder="https://your-app.com/webhook" className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent transition-all" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Setup Completed URL</label>
                <input type="url" value={setupCompletedUrl} onChange={(e) => setSetupCompletedUrl(e.target.value)} placeholder="https://your-app.com/setup-complete" className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent transition-all" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Setup Instructions</label>
                <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Provide setup instructions..." rows={3} className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent transition-all resize-none" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Auth URL</label>
                <input type="url" value={authUrl} onChange={(e) => setAuthUrl(e.target.value)} placeholder="https://your-app.com/auth" className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent transition-all" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">App Home URL</label>
                <input type="url" value={appHomeUrl} onChange={(e) => setAppHomeUrl(e.target.value)} placeholder="https://your-app.com" className="w-full rounded-[0.5rem] bg-white/10 border border-white/20 px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-lime-500 focus:border-transparent transition-all" />
              </div>
            </div>
          </div>
        )}

        {/* Notification Scopes */}
        {isCapabilitySelectedById('proactive_notification') && (
          <div className="bg-white/5 backdrop-blur-sm rounded-[0.5rem] border border-white/10 p-8">
            <div className="flex items-center space-x-3 mb-6">
                <div className="h-10 w-10 rounded-[0.5rem] bg-gradient-to-r from-red-500 to-rose-600 flex items-center justify-center">
                    <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                </div>
                <div>
                    <h3 className="text-xl font-semibold text-white">Notification Scopes</h3>
                    <p className="text-sm text-gray-400">Define notification permissions</p>
                </div>
            </div>
            <div className="flex flex-wrap gap-3">
              {getNotificationScopes().map((scope) => (
                <button
                  key={scope.id}
                  onClick={() => toggleScope(scope)}
                  className={`rounded-[0.5rem] px-4 py-2 text-sm font-medium transition-colors ${ 
                    isScopeSelected(scope) 
                    ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-md' 
                    : 'bg-white/10 text-gray-300 hover:bg-white/20'
                  }`}
                >
                  {scope.title}
                  {isScopeSelected(scope) && <span className="ml-1">✓</span>}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* App Privacy */}
        <div className="bg-white/5 backdrop-blur-sm rounded-[0.5rem] border border-white/10 p-8">
          <div className="flex items-center space-x-3 mb-6">
            <div className="h-10 w-10 rounded-[0.5rem] bg-gradient-to-r from-purple-500 to-pink-600 flex items-center justify-center">
              <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <div>
              <h3 className="text-xl font-semibold text-white">Privacy & Terms</h3>
              <p className="text-sm text-gray-400">Configure app visibility and agree to terms</p>
            </div>
          </div>
          
          <div className="space-y-4">
            <div className="flex items-start space-x-3">
              <input
                type="checkbox"
                id="makePublic"
                checked={makeAppPublic}
                onChange={(e) => setMakeAppPublic(e.target.checked)}
                className="mt-1 h-4 w-4 rounded-[0.5rem] border-gray-600 bg-gray-700 text-blue-600 focus:ring-2 focus:ring-blue-500"
              />
              <div>
                <label htmlFor="makePublic" className="text-white font-medium">Make my app public</label>
                <p className="text-sm text-gray-400 mt-1">Allow other users to discover and use your app</p>
              </div>
            </div>

            <div className="flex items-start space-x-3">
              <input
                type="checkbox"
                id="termsAgreed"
                checked={termsAgreed}
                onChange={(e) => setTermsAgreed(e.target.checked)}
                className="mt-1 h-4 w-4 rounded-[0.5rem] border-gray-600 bg-gray-700 text-blue-600 focus:ring-2 focus:ring-blue-500"
              />
              <div>
                <label htmlFor="termsAgreed" className="text-white font-medium">Agree to Terms of Service <span className="text-red-400">*</span></label>
                <p className="text-sm text-gray-400 mt-1">
                  By submitting this app, I agree to the{' '}
                  <a href="https://omi.me/pages/terms-of-service" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 underline">Omi AI Terms of Service</a>
                  {' '}and{' '}
                  <a href="https://omi.me/pages/privacy" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 underline">Privacy Policy</a>
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Submit Button */}
        <div className="bg-white/5 backdrop-blur-sm rounded-[0.5rem] border border-white/10 p-8">
          <div className="flex items-center space-x-3 mb-6">
            <div className="h-10 w-10 rounded-[0.5rem] bg-gradient-to-r from-green-500 to-emerald-600 flex items-center justify-center">
              <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h3 className="text-xl font-semibold text-white">Submit Your App</h3>
              <p className="text-sm text-gray-400">Review and submit your application</p>
            </div>
          </div>

          {!isValid && (
            <div className="mb-6 rounded-[0.5rem] bg-red-900/20 border border-red-500/30 p-4">
              <div className="flex items-center space-x-2">
                <svg className="h-5 w-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
                <span className="text-sm text-red-300">Please complete all required fields to submit your app</span>
              </div>
            </div>
          )}

          <button
            onClick={() => {
              console.log('🔵 [Submit Button Clicked] Current states:', { isValid, isSubmitting, submissionStarted, submissionRefCurrent: submissionRef.current });
              if (!isValid || isSubmitting || submissionStarted || submissionRef.current) {
                 console.warn('⚠️ [Submit Button Clicked] Action blocked by guards.');
                 return;
              }
              if (showSubmitAppConfirmation) {
                setShowSubmitDialog(true);
              } else {
                handleSubmit();
              }
            }}
            disabled={!isValid || isSubmitting || submissionStarted || submissionRef.current}
            className={`w-full rounded-[0.5rem] py-4 px-6 font-semibold text-lg transition-all duration-200 ${
              isValid && !isSubmitting && !submissionStarted && !submissionRef.current
                ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white hover:from-blue-700 hover:to-purple-700 shadow-lg hover:shadow-xl transform hover:-translate-y-0.5'
                : 'bg-gray-700 text-gray-400 cursor-not-allowed'
            }`}
          >
            {isSubmitting ? (
              <div className="flex items-center justify-center space-x-3">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></div>
                <span>Submitting App...</span>
              </div>
            ) : 'Submit App'}
          </button>
        </div>

        {/* Submit Confirmation Dialog */}
        {showSubmitDialog && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-gray-900 rounded-[0.5rem] p-6 max-w-md w-full border border-white/10 shadow-2xl">
              <h3 className="text-xl font-bold text-white mb-4">Submit App?</h3>
              <p className="text-gray-300 mb-6">
                {makeAppPublic
                  ? 'Your app will be reviewed and made public. You can start using it immediately, even during the review!'
                  : 'Your app will be reviewed and made available to you privately. You can start using it immediately, even during the review!'}
              </p>
              
              <div className="flex items-center mb-6">
                <input
                  type="checkbox"
                  id="dontShowAgain"
                  checked={!showSubmitAppConfirmation} 
                  onChange={(e) => setShowSubmitAppConfirmation(!e.target.checked)}
                  className="mr-3 h-4 w-4 rounded-[0.5rem] border-gray-600 bg-gray-700 text-blue-600 focus:ring-2 focus:ring-blue-500"
                />
                <label htmlFor="dontShowAgain" className="text-gray-300 text-sm">Don't show this dialog again</label>
              </div>
              
              <div className="flex space-x-3">
                <button
                  onClick={() => {
                    console.log('🔵 [Dialog Cancel Clicked]');
                    setShowSubmitDialog(false);
                  }}
                  disabled={isSubmitting} 
                  className="flex-1 py-3 px-4 rounded-[0.5rem] bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    console.log('🔵 [Dialog Submit Clicked] Current states:', { isSubmitting, submissionStarted, submissionRefCurrent: submissionRef.current });
                    if (isSubmitting || submissionStarted || submissionRef.current) {
                       console.warn('⚠️ [Dialog Submit Clicked] Action blocked by guards.');
                       return;
                    }
                    setShowSubmitDialog(false);
                    handleSubmit();
                  }}
                  disabled={isSubmitting || submissionStarted || submissionRef.current} 
                  className="flex-1 py-3 px-4 rounded-[0.5rem] bg-gradient-to-r from-blue-600 to-purple-600 text-white hover:from-blue-700 hover:to-purple-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSubmitting ? (
                    <div className="flex items-center justify-center space-x-3">
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></div>
                      <span>Submitting...</span>
                    </div>
                  ) : 'Submit'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
