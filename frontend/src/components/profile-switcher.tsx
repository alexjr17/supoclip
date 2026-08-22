"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, ChevronDown, Loader2, Plus, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import {
  createProfile,
  fetchProfiles,
  setActiveProfileId,
  type Profile,
} from "@/lib/profiles";

interface ProfileSwitcherProps {
  compact?: boolean;
}

function ProfileAvatar({
  profile,
  compact = false,
}: {
  profile: Profile;
  compact?: boolean;
}) {
  const initial = (profile.name || "C").charAt(0).toUpperCase();
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-full bg-stone-900 text-white font-semibold",
        compact ? "w-6 h-6 text-[10px]" : "w-7 h-7 text-xs",
      )}
    >
      {initial}
    </div>
  );
}

export function ProfileSwitcher({ compact = false }: ProfileSwitcherProps) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeProfileId, setActiveProfileIdState] = useState<string | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newProfileName, setNewProfileName] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchProfiles();
      setProfiles(data.profiles);
      setActiveProfileIdState(data.active_profile_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load channels");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const activeProfile =
    profiles.find((profile) => profile.id === activeProfileId) ?? profiles[0];

  const handleSwitch = (profileId: string) => {
    setActiveProfileId(profileId);
    setActiveProfileIdState(profileId);
    setOpen(false);
    window.location.reload();
  };

  const handleCreate = async () => {
    const name = newProfileName.trim();
    if (!name) return;
    setIsCreating(true);
    setError(null);
    try {
      const profile = await createProfile(name);
      setActiveProfileId(profile.id);
      setActiveProfileIdState(profile.id);
      setNewProfileName("");
      setOpen(false);
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create channel");
    } finally {
      setIsCreating(false);
    }
  };

  if (isLoading && !activeProfile) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 rounded-lg border px-3 text-sm text-gray-500",
          compact ? "py-1" : "py-2",
        )}
      >
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Channels</span>
      </div>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex items-center gap-2 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 transition-colors text-left",
            compact ? "px-2 py-1" : "px-3 py-1.5",
          )}
        >
          {activeProfile && <ProfileAvatar profile={activeProfile} compact={compact} />}
          <span className="hidden sm:block text-sm font-medium text-black max-w-[140px] truncate">
            {activeProfile?.name ?? "Channels"}
          </span>
          <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="p-3 border-b">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Publishing channels
          </p>
        </div>

        <div className="max-h-64 overflow-y-auto p-1">
          {profiles.map((profile) => (
            <button
              key={profile.id}
              type="button"
              onClick={() => handleSwitch(profile.id)}
              className="w-full flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-gray-50 transition-colors text-left"
            >
              <ProfileAvatar profile={profile} compact />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-black truncate">
                  {profile.name}
                </p>
                <p className="text-xs text-gray-500">
                  {profile.accounts.youtube.connected ? "YouTube" : "No YouTube"}
                  {profile.accounts.youtube.connected && profile.accounts.tiktok.connected
                    ? " · "
                    : " · "}
                  {profile.accounts.tiktok.connected ? "TikTok" : "No TikTok"}
                </p>
              </div>
              {profile.id === activeProfileId && (
                <Check className="w-4 h-4 text-black" />
              )}
            </button>
          ))}
        </div>

        <Separator />

        <div className="p-3 space-y-2">
          <div className="flex items-center gap-2">
            <Input
              ref={inputRef}
              value={newProfileName}
              onChange={(event) => setNewProfileName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") handleCreate();
              }}
              placeholder="New channel name"
              className="h-8 text-sm"
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 px-2"
              onClick={handleCreate}
              disabled={isCreating || !newProfileName.trim()}
            >
              {isCreating ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Plus className="w-3.5 h-3.5" />
              )}
            </Button>
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <Link
            href="/settings"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <Settings className="w-4 h-4" />
            Manage channels & accounts
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
