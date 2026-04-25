"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import {
  LayoutGrid,
  Package2,
  Users,
  LogOut,
  CreditCard,
  CheckSquare,
  DollarSign,
  Building2,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
  Megaphone,
  Truck,
  Bell,
  BarChart3,
  ShieldAlert,
  FlaskConical,
  Rocket,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/auth-provider";

export function DashboardSidebar() {
  const pathname = usePathname();
  const { signOut } = useAuth();
  const [isCollapsed, setIsCollapsed] = useState(false);

  // Load collapsed state from localStorage on mount
  useEffect(() => {
    const savedState = localStorage.getItem('sidebarCollapsed');
    if (savedState !== null) {
      setIsCollapsed(savedState === 'true');
    }
  }, []);

  // Save collapsed state to localStorage
  const toggleCollapse = () => {
    const newState = !isCollapsed;
    setIsCollapsed(newState);
    localStorage.setItem('sidebarCollapsed', String(newState));
  };
  
  const navItems = [
    {
      title: "Dashboard",
      href: "/dashboard",
      icon: LayoutGrid,
    },
    {
      title: "Apps",
      href: "/dashboard/apps",
      icon: Package2,
    },
    {
      title: "Summary Apps",
      href: "/dashboard/summary-apps",
      icon: MessageSquare,
    },
    {
      title: "Reviews",
      href: "/dashboard/reviews",
      icon: CheckSquare,
    },
    {
      title: "Subscriptions",
      href: "/dashboard/subscriptions",
      icon: CreditCard,
    },
    {
      title: "App Payouts",
      href: "/dashboard/payouts",
      icon: DollarSign,
    },
    {
      title: "Organizations",
      href: "/dashboard/organizations",
      icon: Building2,
    },
    {
      title: "Team",
      href: "/dashboard/team",
      icon: Users,
    },
    {
      title: "Announcements",
      href: "/dashboard/announcements",
      icon: Megaphone,
    },
    {
      title: "Notifications",
      href: "/dashboard/notifications",
      icon: Bell,
    },
    {
      title: "Analytics",
      href: "/dashboard/analytics",
      icon: BarChart3,
    },
    {
      title: "Releases",
      href: "/dashboard/releases",
      icon: Rocket,
    },
    {
      title: "Chat Lab",
      href: "/dashboard/chat-lab",
      icon: FlaskConical,
    },
    {
      title: "Distributors",
      href: "/dashboard/distributors",
      icon: Truck,
    },
    {
      title: "Fair Use",
      href: "/dashboard/fair-use",
      icon: ShieldAlert,
    },
  ];

  const handleLogout = async () => {
    await signOut();
  };

  return (
    <aside className={cn(
      "border-r bg-card h-screen flex-shrink-0 sticky top-0 flex flex-col z-20 transition-all duration-300",
      isCollapsed ? "w-16" : "w-64"
    )}>
      <div className={cn(
        "border-b h-14 flex items-center transition-all duration-300 relative",
        isCollapsed ? "px-2 justify-center" : "px-4 justify-between"
      )}>
        <Link 
          href="/dashboard" 
          className={cn(
            "flex items-center space-x-2 font-semibold transition-all duration-200",
            isCollapsed ? "justify-center" : "justify-start"
          )}
        >
          <Package2 className="h-6 w-6 flex-shrink-0" />
          <span className={cn(
            "transition-opacity duration-200 whitespace-nowrap",
            isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
          )}>
            OMI Admin
          </span>
        </Link>
        <Button
          variant="ghost"
          size="icon"
          className={cn(
            "h-8 w-8 flex-shrink-0",
            isCollapsed && "absolute top-1/2 -right-3 translate-y-[-50%] bg-background border border-border rounded-full shadow-sm z-10"
          )}
          onClick={toggleCollapse}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {isCollapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>
      <div className="flex-1 py-6 flex flex-col justify-between">
        <nav className="px-2 space-y-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center px-2 py-2 rounded-md text-sm font-medium transition-colors",
                isCollapsed ? "justify-center" : "justify-start",
                pathname === item.href
                  ? "bg-primary/10 text-primary"
                  : "text-foreground hover:bg-accent hover:text-accent-foreground"
              )}
              title={isCollapsed ? item.title : undefined}
            >
              <item.icon className="h-5 w-5 flex-shrink-0" />
              <span className={cn(
                "transition-opacity duration-200",
                isCollapsed ? "opacity-0 w-0 overflow-hidden ml-0" : "opacity-100 ml-3"
              )}>
                {item.title}
              </span>
            </Link>
          ))}
        </nav>
        <div className="px-2 space-y-1">
          <Button 
            variant="ghost" 
            className={cn(
              "w-full text-muted-foreground transition-colors",
              isCollapsed ? "justify-center" : "justify-start"
            )}
            onClick={handleLogout}
            title={isCollapsed ? "Log out" : undefined}
          >
            <LogOut className="h-5 w-5 flex-shrink-0" />
            <span className={cn(
              "transition-opacity duration-200",
              isCollapsed ? "opacity-0 w-0 overflow-hidden ml-0" : "opacity-100 ml-3"
            )}>
              Log out
            </span>
          </Button>
        </div>
      </div>
    </aside>
  );
}