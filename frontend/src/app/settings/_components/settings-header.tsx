"use client";

import Link from "next/link";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { ProfileSwitcher } from "@/components/profile-switcher";
import { ArrowLeft } from "lucide-react";

interface SettingsHeaderProps {
  user: { name?: string | null; email?: string | null; image?: string | null };
  isAdmin: boolean;
  onSignOut: () => void;
}

export function SettingsHeader({ user, isAdmin, onSignOut }: SettingsHeaderProps) {
  const initial = user.name?.charAt(0) || user.email?.charAt(0) || "U";

  return (
    // Sticky so the channel switcher and Back stay reachable on a long page.
    <header className="sticky top-0 z-30 border-b bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
        <Link href="/">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>

        <div className="flex items-center gap-3">
          {isAdmin && (
            <Link href="/admin">
              <Button variant="outline" size="sm">
                Admin
              </Button>
            </Link>
          )}
          <Button variant="outline" size="sm" onClick={onSignOut}>
            Sign Out
          </Button>
          <ProfileSwitcher />
          <Avatar className="h-8 w-8">
            <AvatarImage src={user.image || ""} />
            <AvatarFallback className="bg-gray-100 text-sm text-black">{initial}</AvatarFallback>
          </Avatar>
          <div className="hidden sm:block">
            <p className="text-sm font-medium text-black">{user.name}</p>
            <p className="text-xs text-gray-500">{user.email}</p>
          </div>
        </div>
      </div>
    </header>
  );
}
