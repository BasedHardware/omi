'use server';
import envConfig from '@/src/constants/envConfig';

export interface ExternalIntegration {
  triggers_on: string;
  webhook_url: string;
  setup_completed_url: string;
  setup_instructions_file_path: string;
  app_home_url: string;
  auth_steps: Array<{
    url: string;
    name: string;
  }>;
}

export interface ProactiveNotification {
  scopes: string[];
}

export interface AppSubmissionData {
  name: string;
  description: string;
  capabilities: string[];
  deleted: boolean;
  uid: string;
  category: string;
  private: boolean;
  is_paid: boolean;
  price: number;
  payment_plan: string | null;
  thumbnails: string[];
  external_integration?: ExternalIntegration;
  chat_prompt?: string;
  memory_prompt?: string;
  proactive_notification?: ProactiveNotification;
}

export interface SubmitAppResponse {
  id: string;
  name: string;
  [key: string]: any;
}

export default async function submitApp(
  formData: FormData
): Promise<SubmitAppResponse | null> {
  const apiUrl = envConfig.API_URL || 'http://localhost:8000';
  
  try {
    // Get token from formData
    const token = formData.get('token') as string;
    
    // Remove token from formData before sending to API
    const apiFormData = new FormData();
    Array.from(formData.entries()).forEach(([key, value]) => {
      if (key !== 'token') {
        apiFormData.append(key, value);
      }
    });
    
    const response = await fetch(`${apiUrl}/v1/apps`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: apiFormData,
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ 
        detail: 'Failed to parse error response' 
      }));
      console.error('Failed to submit app:', response.status, errorData);
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error submitting app:', error);
    throw error;
  }
} 