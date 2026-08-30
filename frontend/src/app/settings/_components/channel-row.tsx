"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2, Music2, Pencil, Trash2, Unlink, Youtube } from "lucide-react";

import type { ConnectedAccountSummary, Profile } from "@/lib/profiles";
import type { ChannelPlatform } from "../_hooks/use-publishing-channels";

interface ConnectedAccountProps {
  icon: React.ReactNode;
  label: string;
  account: ConnectedAccountSummary;
  primaryText: string | null;
  secondaryText?: string | null;
  isBusy: boolean;
  disabled: boolean;
  onDisconnect: () => void;
}

function ConnectedAccount({
  icon,
  label,
  account,
  primaryText,
  secondaryText,
  isBusy,
  disabled,
  onDisconnect,
}: ConnectedAccountProps) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
      <div className="flex min-w-0 items-center gap-2">
        {icon}
        {account.connected ? (
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-black">{primaryText}</p>
            {secondaryText && (
              <p className="truncate text-[10px] text-gray-500">{secondaryText}</p>
            )}
          </div>
        ) : (
          <span className="text-xs text-gray-500">Not connected</span>
        )}
      </div>
      {account.connected && (
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5 text-gray-500 hover:text-red-600"
          onClick={onDisconnect}
          disabled={disabled}
          aria-label={label}
        >
          {isBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Unlink className="h-3 w-3" />}
        </Button>
      )}
    </div>
  );
}

interface ChannelRowProps {
  profile: Profile;
  isActive: boolean;
  busy: string | null;
  onRename: (profileId: string, name: string) => Promise<boolean>;
  onDisconnect: (profileId: string, platform: ChannelPlatform) => void;
  onDelete: (profileId: string) => void;
}

/**
 * One publishing channel: its name, its badges, and the YouTube/TikTok
 * accounts attached to it. Rename is local state so editing one row never
 * re-renders or resets the others.
 */
export function ChannelRow({
  profile,
  isActive,
  busy,
  onRename,
  onDisconnect,
  onDelete,
}: ChannelRowProps) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [draftName, setDraftName] = useState(profile.name);

  const isLocked = busy !== null;

  const submitRename = async () => {
    const name = draftName.trim();
    if (!name || isLocked) return;
    // Only leave edit mode when the rename actually landed, so a failed
    // request keeps the user's text instead of silently discarding it.
    if (await onRename(profile.id, name)) {
      setIsRenaming(false);
    }
  };

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {isRenaming ? (
            <Input
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void submitRename();
                if (event.key === "Escape") {
                  setDraftName(profile.name);
                  setIsRenaming(false);
                }
              }}
              autoFocus
              className="h-8 w-48 text-sm"
              aria-label={`New name for ${profile.name}`}
            />
          ) : (
            <p className="truncate text-sm font-medium text-black">{profile.name}</p>
          )}
          {profile.is_default && (
            <Badge variant="outline" className="h-5 px-1.5 py-0 text-[10px]">
              Default
            </Badge>
          )}
          {isActive && (
            <Badge className="h-5 bg-stone-900 px-1.5 py-0 text-[10px] text-white">Active</Badge>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {isRenaming ? (
            <Button
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => void submitRename()}
              disabled={isLocked || !draftName.trim()}
            >
              {/* Swapping an element for a bare text node breaks under page
                  translators, which replace text nodes with their own wrappers.
                  Both branches render an element so React never has to. */}
              {busy === `rename-${profile.id}` ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <span>Save</span>
              )}
            </Button>
          ) : (
            <>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2"
                onClick={() => {
                  setDraftName(profile.name);
                  setIsRenaming(true);
                }}
                disabled={isLocked}
                aria-label={`Rename ${profile.name}`}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              {!profile.is_default && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-red-600 hover:text-red-700"
                  onClick={() => onDelete(profile.id)}
                  disabled={isLocked}
                  aria-label={`Delete ${profile.name}`}
                >
                  {busy === `delete-${profile.id}` ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <ConnectedAccount
          icon={<Youtube className="h-4 w-4 shrink-0 text-red-500" />}
          label={`Disconnect YouTube for ${profile.name}`}
          account={profile.accounts.youtube}
          primaryText={profile.accounts.youtube.title ?? "YouTube"}
          secondaryText={
            profile.accounts.youtube.handle ? `@${profile.accounts.youtube.handle}` : null
          }
          isBusy={busy === `disconnect-${profile.id}-youtube`}
          disabled={isLocked}
          onDisconnect={() => onDisconnect(profile.id, "youtube")}
        />
        <ConnectedAccount
          icon={<Music2 className="h-4 w-4 shrink-0 text-gray-500" />}
          label={`Disconnect TikTok for ${profile.name}`}
          account={profile.accounts.tiktok}
          primaryText={profile.accounts.tiktok.display_name ?? "TikTok"}
          isBusy={busy === `disconnect-${profile.id}-tiktok`}
          disabled={isLocked}
          onDisconnect={() => onDisconnect(profile.id, "tiktok")}
        />
      </div>
    </div>
  );
}
