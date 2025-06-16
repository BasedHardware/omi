interface LoadingStateProps {
  isRedirecting: boolean;
  isSubmitting: boolean;
}

export default function LoadingState({ isRedirecting, isSubmitting }: LoadingStateProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0B0F17] text-white">
      <div className="text-center">
        <div className="mb-6 h-8 w-8 mx-auto animate-spin rounded-full border-2 border-gray-600 border-t-white"></div>
        
        <p className="text-lg font-medium text-white">
          {isRedirecting 
            ? 'App submitted successfully!' 
            : isSubmitting 
            ? 'Submitting your app...' 
            : 'Loading...'}
        </p>
        
        {(isSubmitting || isRedirecting) && (
          <p className="text-sm text-gray-400 mt-2">
            {isRedirecting 
              ? 'Redirecting to homepage...'
              : 'Please wait while we process your submission'}
          </p>
        )}
      </div>
    </div>
  );
}