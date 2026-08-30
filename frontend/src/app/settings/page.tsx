"use client";

import { useState } from "react";
import Link from "next/link";
import { CreditCard, Music2, Settings, Share2, Type, Youtube } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CustomFontFaces } from "@/components/custom-font-faces";
import { signOut, useSession } from "@/lib/auth-client";

import { BillingSection } from "./_components/billing-section";
import { CaptionDefaultsSection } from "./_components/caption-defaults-section";
import { DeveloperSection } from "./_components/developer-section";
import { PlatformConnectionSection } from "./_components/platform-connection-section";
import { PublishingChannelsSection } from "./_components/publishing-channels-section";
import { SettingsHeader } from "./_components/settings-header";
import { useBillingSummary } from "./_hooks/use-billing-summary";
import { useClipDefaults } from "./_hooks/use-clip-defaults";
import { usePlatformConnections } from "./_hooks/use-platform-connections";
import { usePublishingChannels } from "./_hooks/use-publishing-channels";

export default function SettingsPage() {
  const { data: session, isPending } = useSession();
  const userId = session?.user?.id ?? null;
  const isAdmin = Boolean((session?.user as { is_admin?: boolean } | undefined)?.is_admin);

  const clipDefaults = useClipDefaults(userId, isPending);
  const channels = usePublishingChannels();
  const connections = usePlatformConnections();
  const billing = useBillingSummary(userId);

  const [tab, setTab] = useState("captions");

  const handleSignOut = async () => {
    await signOut();
    window.location.href = "/sign-in";
  };

  if (isPending || clipDefaults.isFetching) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white p-4">
        <div className="space-y-4">
          <Skeleton className="mx-auto h-4 w-32" />
          <Skeleton className="mx-auto h-4 w-48" />
          <Skeleton className="mx-auto h-4 w-24" />
        </div>
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className="min-h-screen bg-white">
        <div className="mx-auto max-w-4xl px-4 py-24">
          <div className="text-center">
            <h1 className="mb-4 text-3xl font-bold text-black">Sign In Required</h1>
            <p className="mb-8 text-gray-600">You need to sign in to access your settings</p>
            <Link href="/sign-in">
              <Button size="lg">Sign In</Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const showBilling = Boolean(billing.summary?.monetization_enabled);

  return (
    <div className="min-h-screen bg-gray-50/50">
      <CustomFontFaces fonts={clipDefaults.fonts} />

      <SettingsHeader user={session.user} isAdmin={isAdmin} onSignOut={handleSignOut} />

      <main className="mx-auto max-w-4xl px-4 py-10">
        <div className="mb-6">
          <div className="mb-1 flex items-center gap-2">
            <Settings className="h-6 w-6 text-black" />
            <h1 className="text-2xl font-bold text-black">Settings</h1>
          </div>
          <p className="text-gray-600">
            Defaults for new clips, the channels you publish to, and your account.
          </p>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="captions">
              <Type />
              Captions
            </TabsTrigger>
            <TabsTrigger value="publishing">
              <Share2 />
              Publishing
            </TabsTrigger>
            <TabsTrigger value="account">
              <CreditCard />
              Account
            </TabsTrigger>
          </TabsList>

          <TabsContent value="captions">
            <CaptionDefaultsSection
              fonts={clipDefaults.fonts}
              fontFamily={clipDefaults.fontFamily}
              onFontFamilyChange={clipDefaults.setFontFamily}
              fontSize={clipDefaults.fontSize}
              onFontSizeChange={clipDefaults.setFontSize}
              fontColor={clipDefaults.fontColor}
              onFontColorChange={clipDefaults.setFontColor}
              completionEmails={clipDefaults.completionEmails}
              onCompletionEmailsChange={clipDefaults.setCompletionEmails}
              isSaving={clipDefaults.isSaving}
              error={clipDefaults.error}
              success={clipDefaults.success}
              onSave={clipDefaults.save}
            />
          </TabsContent>

          <TabsContent value="publishing" className="space-y-6">
            <PublishingChannelsSection
              profiles={channels.profiles}
              activeProfileId={channels.activeProfileId}
              busy={channels.busy}
              error={channels.error}
              onRename={channels.rename}
              onDisconnect={channels.disconnect}
              onDelete={channels.remove}
            />

            <PlatformConnectionSection
              id="youtube"
              platform="youtube"
              label="YouTube publishing"
              icon={<Youtube className="h-4 w-4 text-red-500" />}
              description="Auto-publish generated clips to YouTube at their scheduled time."
              connectedHint="New clips will be uploaded directly to YouTube."
              disconnectedHint="Connect your channel to publish clips directly (free, no monthly cap)."
              fallbackAccountName="YouTube channel"
              connection={connections.youtube}
              activeProfileName={channels.activeProfileName}
              isConnecting={connections.connecting === "youtube"}
              message={connections.messages.youtube}
              onConnect={connections.connect}
            />

            <PlatformConnectionSection
              id="tiktok"
              platform="tiktok"
              label="TikTok publishing"
              icon={<Music2 className="h-4 w-4 text-gray-500" />}
              description="Schedule and auto-publish generated clips to your TikTok account."
              connectedHint="Clips can be scheduled and published to TikTok automatically."
              disconnectedHint="Connect your TikTok account to schedule clips. Requires the video.upload scope and Direct Post (video.publish) for auto-publishing."
              fallbackAccountName="TikTok account"
              connection={connections.tiktok}
              activeProfileName={channels.activeProfileName}
              isConnecting={connections.connecting === "tiktok"}
              message={connections.messages.tiktok}
              onConnect={connections.connect}
            />
          </TabsContent>

          <TabsContent value="account" className="space-y-6">
            <DeveloperSection />

            {showBilling && billing.summary && (
              <BillingSection
                summary={billing.summary}
                isActionLoading={billing.isActionLoading}
                error={billing.error}
                onAction={billing.startAction}
              />
            )}
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
