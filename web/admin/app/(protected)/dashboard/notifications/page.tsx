"use client";

import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart3, ArrowRight } from "lucide-react";
import PromptTester from "./prompt-tester";

export default function NotificationsPage() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Proactive Notifications</h1>
      </div>

      <Card className="p-6">
        <CardHeader className="px-0 pt-0">
          <CardTitle className="flex items-center gap-2 text-lg">
            <BarChart3 className="h-5 w-5" />
            Analytics moved
          </CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0 space-y-4">
          <p className="text-sm text-muted-foreground">
            Notification volume, adoption, DAU overlap, and floating-bar CTR charts now live on the analytics dashboard.
          </p>
          <Link
            href="/dashboard/analytics"
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Open analytics
            <ArrowRight className="h-4 w-4" />
          </Link>
        </CardContent>
      </Card>

      <PromptTester />
    </div>
  );
}
