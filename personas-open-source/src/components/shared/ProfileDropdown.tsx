'use client';

import { useState, useEffect } from 'react';
import { auth } from '@/lib/firebase';
import { signOut } from 'firebase/auth';
import { Avatar, AvatarImage, AvatarFallback, Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';

const ProfileDropdown = ({ user }: { user: any }) => {
  const router = useRouter();

  const handleSignOut = async () => {
    try {
      await signOut(auth);
      toast.success('Signed out successfully!');
      router.push('/');
    } catch (error: any) {
      console.error('Error signing out:', error);
      toast.error('Failed to sign out.');
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger>
        <Avatar className="h-8 w-8">
          <AvatarImage src={user?.photoURL || '/omi-avatar.svg'} alt={user?.displayName || 'User'} />
          <AvatarFallback>{user?.displayName?.charAt(0) || 'U'}</AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{user?.displayName || 'User'}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push('/profile')}>Profile</DropdownMenuItem>
        {/* <DropdownMenuItem>Settings</DropdownMenuItem> */}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleSignOut}>Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default ProfileDropdown;
