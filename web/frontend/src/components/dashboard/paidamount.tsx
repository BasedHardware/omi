'use client';
import envConfig from '@/src/constants/envConfig';

import { useState } from 'react';
import { DollarSign } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/src/components/ui/dialog';
import { Input } from '@/src/components/ui/input';
import { Label } from '@/src/components/ui/label';
import { Button } from '@/src/components/ui/button';

interface Plugin {
  id: string;
  comps: number;
  // Add other necessary properties
}

export default function PaidAmountDialog({ plugin }: { plugin: Plugin }) {
  const [isOpen, setIsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const amount = formData.get('amount') as string;
    //const adminKey = formData.get('adminKey') as string;
    try {
      const response = await fetch(`${envConfig.API_URL}/v1/plugins/report-comp`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${envConfig.ADMIN_KEY}`,
        },
        body: JSON.stringify({
          plugin_id: plugin.id,
          comp_count: parseInt(amount, 10),
        }),
        // mode: 'no-cors',
      });

      console.log(response.status);

      if (!response.ok) {
        if (response.status === 401) {
          console.log('401 found');
          throw new Error('Unauthorized. Please check your admin key.');
        }
        throw new Error('Failed to update paid amount');
      }

      setIsOpen(false);
      // TODO: Update UI or show success message
    } catch (error) {
      console.error('Error updating paid amount:', error);
      if (error instanceof Error) {
        setError(error.message);
      } else {
        setError('Failed to update paid amount. Please try again.');
      }
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <div className="flex cursor-pointer flex-col items-center rounded-lg bg-white p-4 shadow transition-colors hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700">
          <DollarSign className="mb-2 h-8 w-8 text-purple-500" />
          <span className="text-2xl font-bold text-gray-800 dark:text-white">
            ${plugin.comps || 0}
          </span>
          <span className="text-gray-600 dark:text-gray-400">Paid Out</span>
        </div>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Set Paid Amount</DialogTitle>
          <DialogDescription>
            Enter the amount to be set as paid out and provide the admin key.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="amount" className="text-right">
                Amount
              </Label>
              <Input
                id="amount"
                name="amount"
                type="number"
                className="col-span-3"
                step="0.01"
                placeholder="0.00"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="adminKey" className="text-right">
                Admin Key
              </Label>
              <Input
                id="adminKey"
                name="adminKey"
                type="password"
                className="col-span-3"
              />
            </div>
          </div>
          {error && <p className="mb-4 text-red-500">{error}</p>}
          <DialogFooter>
            <Button type="submit">Set Paid Amount</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
