"use client";

import { ThemeToggle } from "@/components/ui/theme-toggle";

export function DashboardHeader() {
  return (
    <header className="h-14 border-b px-4 md:px-6 flex items-center justify-end bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-10">
      <ThemeToggle />
    </header>
  );
}