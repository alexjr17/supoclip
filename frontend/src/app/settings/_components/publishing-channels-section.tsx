"use client";

import { Share2 } from "lucide-react";

import type { Profile } from "@/lib/profiles";

import { ChannelRow } from "./channel-row";
import { ErrorAlert, SettingsSection } from "./settings-section";
import type { ChannelPlatform } from "../_hooks/use-publishing-channels";

interface PublishingChannelsSectionProps {
  profiles: Profile[];
  activeProfileId: string | null;
  busy: string | null;
  error: string | null;
  onRename: (profileId: string, name: string) => Promise<boolean>;
  onDisconnect: (profileId: string, platform: ChannelPlatform) => void;
  onDelete: (profileId: string) => void;
}

export function PublishingChannelsSection({
  profiles,
  activeProfileId,
  busy,
  error,
  onRename,
  onDisconnect,
  onDelete,
}: PublishingChannelsSectionProps) {
  return (
    <SettingsSection
      id="channels"
      icon={<Share2 className="h-4 w-4" />}
      title="Publishing channels"
      description="Each channel owns its own YouTube and TikTok accounts. Use the channel switcher in the top bar to pick which one to publish to."
    >
      <div className="space-y-3">
        {profiles.map((profile) => (
          <ChannelRow
            key={profile.id}
            profile={profile}
            isActive={profile.id === activeProfileId}
            busy={busy}
            onRename={onRename}
            onDisconnect={onDisconnect}
            onDelete={onDelete}
          />
        ))}
        {profiles.length === 0 && (
          <p className="text-sm text-gray-500">
            No publishing channels yet. Create one with the channel switcher.
          </p>
        )}
      </div>

      {error && <ErrorAlert>{error}</ErrorAlert>}
    </SettingsSection>
  );
}
