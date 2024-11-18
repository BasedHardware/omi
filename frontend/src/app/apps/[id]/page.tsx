// import { useState, useEffect } from 'react';
import envConfig from '@/src/constants/envConfig';
import { Star, Download, DollarSign, Moon, Sun, ArrowLeft } from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/src/components/ui/card';
import { Progress } from '@/src/components/ui/progress';
import Link from 'next/link';

import { Button } from '@/src/components/ui/button';
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
import PaidAmountDialog from '@/src/components/dashboard/paidamount';
import { PluginStat, Plugin } from '../page';

const COST_CONSTANT = 0.05;

export default async function PluginDetailView({ params }: { params: { id: string } }) {
  // const [darkMode, setDarkMode] = useState(false);
  var response = await fetch(`${envConfig.API_URL}/v1/approved-apps?include_reviews=true`);
  const plugins = (await response.json()) as Plugin[];

  // Get params in a server component
  const { id } = params;

  const plugin = plugins.find((p) => p.id === id);

  if (!plugin) {
    throw new Error('App not found');
  }

  response = await fetch("https://raw.githubusercontent.com/BasedHardware/omi/refs/heads/main/community-plugin-stats.json");
  const stats = (await response.json()) as PluginStat[];
  const stat = stats.find((p) => p.id === id);

  // useEffect(() => {
  //   if (darkMode) {
  //     document.documentElement.classList.add('dark');
  //   } else {
  //     document.documentElement.classList.remove('dark');
  //   }
  // }, [darkMode]);

  return (
    <div className="bg-gray-100 transition-colors duration-300 dark:bg-gray-900">
      <div className="container mx-auto p-4">
        <div className="mb-6 flex items-center justify-between">
          <Link
            href="/apps"
            className="pt-8 flex items-center text-gray-600 transition-colors hover:text-gray-800 dark:text-gray-300 dark:hover:text-white"
          >
            <ArrowLeft className="mr-2" />
            Back to Apps
          </Link>
          {/* <button
            variant="outline"
            size="icon"
            onClick={() => setDarkMode(!darkMode)}
            className="rounded-full"
          >
            {darkMode ? (
              <Sun className="h-[1.2rem] w-[1.2rem]" />
            ) : (
              <Moon className="h-[1.2rem] w-[1.2rem]" />
            )}
            <span className="sr-only">Toggle theme</span>
          </button> */}
        </div>

        <Card className="mb-8">
          <CardHeader>
            <div className="mb-4 flex items-center">
              <img
                src={plugin.image}
                alt={plugin.name}
                className="mr-6 h-24 w-24 rounded-full object-cover"
              />
              <div>
                <CardTitle className="mb-2 text-3xl font-bold text-gray-800 dark:text-white">
                  {plugin.name}
                </CardTitle>
                <CardDescription className="text-lg text-gray-600 dark:text-gray-400">
                  by {plugin.author}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="mb-6 text-gray-700 dark:text-gray-300">{plugin.description}</p>
            <div className="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2">
              <div className="flex flex-col items-center rounded-lg bg-white p-4 shadow dark:bg-gray-800">
                <Download className="mb-2 h-8 w-8 text-blue-500" />
                <span className="text-2xl font-bold text-gray-800 dark:text-white">
                  {plugin.installs.toLocaleString()}
                </span>
                <span className="text-gray-600 dark:text-gray-400">Installs</span>
              </div>
              <div className="flex flex-col items-center rounded-lg bg-white p-4 shadow dark:bg-gray-800">
                <DollarSign className="mb-2 h-8 w-8 text-green-500" />
                <span className="text-2xl font-bold text-gray-800 dark:text-white">
                  ${stat == undefined ? 0 : stat.money}
                </span>
                <span className="text-gray-600 dark:text-gray-400">Total Earned</span>
              </div>
              {/* <Dialog>
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
                  <form action={updatePaidAmount}>
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
                    <DialogFooter>
                      <Button type="submit">Set Paid Amount</Button>
                    </DialogFooter>
                  </form>
                </DialogContent>
              </Dialog> */}
              {/*<PaidAmountDialog plugin={plugin} />*/}
            </div>
            <Button className="w-full bg-black text-white hover:bg-gray-800" asChild>
              <Link href={`https://omi.me`}>Try it</Link>
            </Button>
            <div className="mb-2 flex items-center">
              <Star className="mr-2 h-6 w-6 text-yellow-400" />
              <span className="mr-2 text-2xl font-bold text-gray-800 dark:text-white">
                {(plugin.rating_avg ?? 0).toFixed(1)}
              </span>
              <span className="text-gray-600 dark:text-gray-400">
                ({plugin.rating_count} ratings)
              </span>
            </div>
            <Progress value={plugin.rating_avg * 20} className="mb-6 h-2" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// import { revalidatePath } from 'next/cache';

// async function updatePaidAmount(formData: FormData) {
//   'use server';

//   const amount = formData.get('amount') as string;
//   const adminKey = formData.get('adminKey') as string;
//   const pluginId = formData.get('pluginId') as string;

//   try {
//     const response = await fetch('http://0.0.0.0:8000/v1/plugins/report-comp', {
//       method: 'POST',
//       headers: {
//         'Content-Type': 'application/json',
//         Authorization: `Bearer ${adminKey}`,
//       },
//       body: JSON.stringify({
//         plugin_id: pluginId,
//         comp_count: parseInt(amount, 10),
//       }),
//     });
//     if (!response.ok) {
//       if (response.status === 401) {
//         return { success: false, error: 'Unauthorized. Please check your admin key.' };
//       }
//       throw new Error('Failed to update paid amount');
//     }

//     // revalidatePath(`/dashboard/${pluginId}`);
//     return { success: true };
//   } catch (error) {
//     console.error('Error updating paid amount:', error);
//     return { success: false, error: 'Failed to update paid amount' };
//   }
// }
