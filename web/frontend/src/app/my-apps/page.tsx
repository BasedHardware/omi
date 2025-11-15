'use client';

import { useAuth } from '../../hooks/useAuth';
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';
import envConfig from '@/src/constants/envConfig';

interface App {
  id: string;
  name: string;
  description: string;
  icon_url?: string;
  deleted?: boolean;
}

export default function MyAppsPage() {
  const { user, loading: authLoading, signOut } = useAuth();
  const router = useRouter();
  const [apps, setApps] = useState<App[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) {
      console.log('[MyAppsPage] User not authenticated, redirecting to /');
      router.push('/');
    }
  }, [user, authLoading, router]);

  const fetchUserApps = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    console.log("🚀 [fetchUserApps] Fetching user's apps...");
    if (!user) return;

    try {
      const token = await user.getIdToken();
      if (!token) {
        throw new Error('Authentication token not available.');
      }
      const response = await fetch(
        `${envConfig.API_URL || 'http://localhost:8000'}/v1/apps`,
        { headers: { Authorization: `Bearer ${token}` } },
      );

      console.log('📡 [fetchUserApps] Backend response status:', response.status);
      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => ({ detail: 'Failed to parse error response' }));
        throw new Error(errorData.detail || `HTTP error ${response.status}`);
      }

      const userApps: App[] = await response.json();
      setApps(userApps.filter((app) => !app.deleted));
      console.log('✅ [fetchUserApps] Apps fetched successfully:', userApps.length);
    } catch (err) {
      console.error('❌ [fetchUserApps] Error fetching apps:', err);
      setError((err as Error).message || 'Failed to fetch apps. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (user) {
      fetchUserApps();
    }
  }, [user, fetchUserApps]);

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-[#0B0F17] to-gray-800 pt-16">
      {/* Header */}
      <div className="fixed left-0 right-0 top-16 z-40 border-b border-white/10 bg-[#0B0F17]/80 backdrop-blur-md">
        <div className="mx-auto max-w-5xl px-6 py-4">
          {' '}
          {/* Adjusted max-w for potentially wider content */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-6">
              <Link
                href="/apps"
                className="group flex items-center space-x-2 text-gray-400 transition-colors hover:text-white"
              >
                <svg
                  className="h-5 w-5 transition-transform group-hover:-translate-x-1"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 19l-7-7 7-7"
                  />
                </svg>
                <span>Back to Apps</span>
              </Link>
              <div>
                <h1 className="bg-gradient-to-r from-white to-gray-300 bg-clip-text text-2xl font-bold text-transparent">
                  My Apps
                </h1>
                <p className="text-sm text-gray-400">Manage your created applications</p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-r from-blue-500 to-purple-600 text-sm font-medium text-white">
                  {user.displayName?.charAt(0) || user.email?.charAt(0) || 'U'}
                </div>
                <span className="hidden text-sm text-gray-300 sm:block">
                  {user.displayName || user.email}
                </span>
              </div>
              <button
                onClick={signOut}
                className="text-sm text-gray-400 transition-colors hover:text-white"
              >
                Sign Out
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="mx-auto mt-20 max-w-5xl px-6 py-8">
        {' '}
        {/* Added mt-20 for fixed header + extra space */}
        {error && (
          <div className="mb-6 rounded-lg border border-red-500/50 bg-red-900/30 p-4 text-center">
            <p className="text-red-300">{error}</p>
            <button
              onClick={fetchUserApps}
              className="mt-2 rounded-md bg-red-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-600"
            >
              Retry
            </button>
          </div>
        )}
        {apps.length === 0 && !isLoading && !error && (
          <div className="py-10 text-center">
            <svg
              className="mx-auto h-12 w-12 text-gray-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                vectorEffect="non-scaling-stroke"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"
              />
            </svg>
            <h3 className="mt-2 text-xl font-semibold text-white">No apps created yet</h3>
            <p className="mt-1 text-sm text-gray-400">
              You haven&apos;t created any apps. Get started by creating your first one.
            </p>
            <div className="mt-6">
              <Link
                href="/create-app"
                className="inline-flex items-center rounded-md border border-transparent bg-gradient-to-r from-blue-600 to-purple-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:from-blue-700 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-800"
              >
                <svg
                  className="-ml-1 mr-2 h-5 w-5"
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z"
                    clipRule="evenodd"
                  />
                </svg>
                Create New App
              </Link>
            </div>
          </div>
        )}
        {apps.length > 0 && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {apps.map((app) => (
              <Link key={app.id} href={`/apps/${app.id}`} className="group block">
                <div className="rounded-xl border border-white/10 bg-white/5 p-6 backdrop-blur-sm transition-all duration-300 ease-in-out group-hover:-translate-y-1 group-hover:border-white/20 group-hover:bg-white/10 group-hover:shadow-xl">
                  <div className="flex items-start space-x-4">
                    <div className="flex-shrink-0">
                      {app.icon_url ? (
                        <Image
                          src={app.icon_url}
                          alt={`${app.name} icon`}
                          width={48}
                          height={48}
                          className="rounded-lg object-cover"
                        />
                      ) : (
                        <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-gray-600 bg-gradient-to-br from-gray-700 to-gray-800">
                          <span className="text-xl font-bold text-white">
                            {app.name.charAt(0).toUpperCase()}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate text-lg font-semibold text-white transition-colors group-hover:text-blue-400">
                        {app.name}
                      </h3>
                      <p className="truncate-2-lines mt-1 text-sm text-gray-400">
                        {app.description}
                      </p>
                    </div>
                    <svg
                      className="h-5 w-5 text-gray-400 opacity-0 transition-opacity group-hover:opacity-100"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Add a CSS class for multi-line truncation if not using Tailwind plugin
// In your global CSS or a style tag:
// .truncate-2-lines {
//   display: -webkit-box;
//   -webkit-line-clamp: 2;
//   -webkit-box-orient: vertical;
//   overflow: hidden;
// }
