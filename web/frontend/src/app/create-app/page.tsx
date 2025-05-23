'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { useAuth } from '@/src/context/AuthContext';

export default function CreateAppPage() {
  const router = useRouter();
  const { user, loading, getIdToken } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login');
    }
  }, [user, loading, router]);

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    category: 'utility',
    capabilities: ['chat'],
    instructions: '',
    author: '',
    email: '',
    is_paid: false,
    price: 0,
    payment_plan: 'one-time',
  });
  const [thumbnail, setThumbnail] = useState<File | null>(null);
  const [thumbnailPreview, setThumbnailPreview] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const categories = [
    { value: 'utility', label: 'Utility' },
    { value: 'productivity', label: 'Productivity' },
    { value: 'entertainment', label: 'Entertainment' },
    { value: 'education', label: 'Education' },
    { value: 'social', label: 'Social' },
    { value: 'health', label: 'Health & Fitness' },
    { value: 'finance', label: 'Finance' },
    { value: 'other', label: 'Other' },
  ];

  const capabilities = [
    { value: 'chat', label: 'Chat' },
    { value: 'voice', label: 'Voice' },
    { value: 'image', label: 'Image' },
    { value: 'video', label: 'Video' },
    { value: 'file', label: 'File' },
  ];

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      const checked = (e.target as HTMLInputElement).checked;
      setFormData({ ...formData, [name]: checked });
    } else {
      setFormData({ ...formData, [name]: value });
    }
  };

  const handleCapabilityChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { value, checked } = e.target;
    if (checked) {
      setFormData({
        ...formData,
        capabilities: [...formData.capabilities, value],
      });
    } else {
      setFormData({
        ...formData,
        capabilities: formData.capabilities.filter((cap) => cap !== value),
      });
    }
  };

  const handleThumbnailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setThumbnail(file);
      setThumbnailPreview(URL.createObjectURL(file));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!thumbnail) {
      setError('Please upload an app thumbnail');
      return;
    }

    setIsSubmitting(true);
    setError('');

    try {
      const idToken = await getIdToken();
      if (!idToken) {
        throw new Error('You must be logged in to create an app');
      }

      const adminKey = process.env.NEXT_PUBLIC_ADMIN_KEY || 'test123';
      const authHeader = idToken ? `Bearer ${idToken}` : `Bearer ${adminKey}`;

      const data = new FormData();
      data.append('app_data', JSON.stringify(formData));
      data.append('file', thumbnail);

      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/v1/apps`, {
        method: 'POST',
        headers: {
          Authorization: authHeader,
        },
        body: data,
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create app');
      }
      setSuccess('App submitted successfully! It will be reviewed by our team.');
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-900 text-white">
        <div className="text-center">
          <div className="mb-4 h-12 w-12 animate-spin rounded-full border-t-2 border-white"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-900 px-4 py-20 text-white">
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-8 text-center text-3xl font-bold">Create Your Omi App</h1>
        {error && (
          <div className="mb-6 rounded border border-red-500 bg-red-900/50 px-4 py-3 text-white">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-6 rounded border border-green-500 bg-green-900/50 px-4 py-3 text-white">
            {success}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-6">
              <div>
                <label htmlFor="name" className="mb-1 block text-sm font-medium">
                  App Name *
                </label>
                <input
                  type="text"
                  id="name"
                  name="name"
                  required
                  value={formData.name}
                  onChange={handleChange}
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div>
                <label htmlFor="category" className="mb-1 block text-sm font-medium">
                  Category *
                </label>
                <select
                  id="category"
                  name="category"
                  required
                  value={formData.category}
                  onChange={handleChange}
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  {categories.map((category) => (
                    <option key={category.value} value={category.value}>
                      {category.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="capabilities" className="mb-1 block text-sm font-medium">
                  Capabilities *
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {capabilities.map((capability) => (
                    <div key={capability.value} className="flex items-center">
                      <input
                        type="checkbox"
                        id={`capability-${capability.value}`}
                        name="capabilities"
                        value={capability.value}
                        checked={formData.capabilities.includes(capability.value)}
                        onChange={handleCapabilityChange}
                        className="mr-2 h-4 w-4 rounded border-gray-700 text-purple-600 focus:ring-purple-500"
                      />
                      <label htmlFor={`capability-${capability.value}`}>
                        {capability.label}
                      </label>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <label htmlFor="author" className="mb-1 block text-sm font-medium">
                  Author Name *
                </label>
                <input
                  type="text"
                  id="author"
                  name="author"
                  required
                  value={formData.author}
                  onChange={handleChange}
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div>
                <label htmlFor="email" className="mb-1 block text-sm font-medium">
                  Contact Email *
                </label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  required
                  value={formData.email}
                  onChange={handleChange}
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>

            <div className="space-y-6">
              <div>
                <label htmlFor="description" className="mb-1 block text-sm font-medium">
                  Description *
                </label>
                <textarea
                  id="description"
                  name="description"
                  required
                  value={formData.description}
                  onChange={handleChange}
                  rows={4}
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div>
                <label htmlFor="instructions" className="mb-1 block text-sm font-medium">
                  Instructions
                </label>
                <textarea
                  id="instructions"
                  name="instructions"
                  value={formData.instructions}
                  onChange={handleChange}
                  rows={4}
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="How to use your app..."
                />
              </div>

              <div>
                <label htmlFor="thumbnail" className="mb-1 block text-sm font-medium">
                  App Thumbnail *
                </label>
                <div className="flex items-center space-x-4">
                  <div className="flex-shrink-0">
                    {thumbnailPreview ? (
                      <Image
                        src={thumbnailPreview}
                        alt="Thumbnail preview"
                        width={80}
                        height={80}
                        className="rounded-md object-cover"
                      />
                    ) : (
                      <div className="flex h-20 w-20 items-center justify-center rounded-md border border-gray-700 bg-gray-800">
                        <span className="text-xs text-gray-500">No image</span>
                      </div>
                    )}
                  </div>
                  <input
                    type="file"
                    id="thumbnail"
                    name="thumbnail"
                    accept="image/*"
                    onChange={handleThumbnailChange}
                    className="block w-full text-sm text-gray-400
                      file:mr-4 file:rounded-md file:border-0
                      file:bg-purple-600 file:text-white
                      hover:file:bg-purple-700"
                  />
                </div>
              </div>
              <div>
                <div className="mb-2 flex items-center">
                  <input
                    type="checkbox"
                    id="is_paid"
                    name="is_paid"
                    checked={formData.is_paid}
                    onChange={handleChange}
                    className="mr-2 h-4 w-4 rounded border-gray-700 text-purple-600 focus:ring-purple-500"
                  />
                  <label htmlFor="is_paid" className="text-sm font-medium">
                    This is a paid app
                  </label>
                </div>
                {formData.is_paid && (
                  <div className="mt-2 grid grid-cols-2 gap-4">
                    <div>
                      <label htmlFor="price" className="mb-1 block text-sm font-medium">
                        Price (USD) *
                      </label>
                      <input
                        type="number"
                        id="price"
                        name="price"
                        required={formData.is_paid}
                        value={formData.price}
                        onChange={handleChange}
                        min="0"
                        step="0.01"
                        className="w-full rounded-md border border-gray-700 bg-gray-800 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                    </div>
                    <div>
                      <label
                        htmlFor="payment_plan"
                        className="mb-1 block text-sm font-medium"
                      >
                        Payment Plan *
                      </label>
                      <select
                        id="payment_plan"
                        name="payment_plan"
                        required={formData.is_paid}
                        value={formData.payment_plan}
                        onChange={handleChange}
                        className="w-full  rounded-md border border-gray-700 bg-gray-800 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
                      >
                        <option value="one-time">One-time purchase</option>
                        <option value="subscription">Subscription</option>
                      </select>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="flex justify-center pt-4">
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-md bg-purple-600 px-8 py-3 font-medium transition-colors hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSubmitting ? 'Submitting...' : 'Submit App'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
