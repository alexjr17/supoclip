"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { signOut, useSession } from "@/lib/auth-client";
import { formatBillingPlanName, getPublicBillingPlans, isPaidBillingPlan, type BillingPlanId } from "@/lib/billing-plans";
import { track } from "@/lib/datafast";
import Link from "next/link";
import { Type, Palette, CheckCircle, AlertCircle, Settings, ArrowLeft, Mail, KeyRound, ChevronRight, Pencil, Trash2, Youtube, Music2, Unlink, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ProfileSwitcher } from "@/components/profile-switcher";
import {
  deleteProfile,
  disconnectAccount,
  fetchProfiles,
  renameProfile,
  type Profile,
} from "@/lib/profiles";

interface UserPreferences {
  fontFamily: string;
  fontSize: number;
  fontColor: string;
  notifyOnCompletion: boolean;
}

interface BillingSummary {
  monetization_enabled: boolean;
  plan: string;
  subscription_status: string;
  subscription_provider: string | null;
  usage_count: number;
  usage_limit: number | null;
  remaining: number | null;
  upgrade_required: boolean;
}

export default function SettingsPage() {
  const [fontFamily, setFontFamily] = useState("TikTokSans-Regular");
  const [fontSize, setFontSize] = useState(24);
  const [fontColor, setFontColor] = useState("#FFFFFF");
  const [completionEmails, setCompletionEmails] = useState(true);
  const [availableFonts, setAvailableFonts] = useState<Array<{ name: string, display_name: string }>>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [billingSummary, setBillingSummary] = useState<BillingSummary | null>(null);
  const [isBillingActionLoading, setIsBillingActionLoading] = useState(false);
  const [youtubeStatus, setYoutubeStatus] = useState<{
    configured: boolean;
    channel: { title?: string; handle?: string } | null;
  } | null>(null);
  const [isYoutubeConnecting, setIsYoutubeConnecting] = useState(false);
  const [youtubeMessage, setYoutubeMessage] = useState<string | null>(null);
  const [tiktokStatus, setTiktokStatus] = useState<{
    configured: boolean;
    user: { display_name?: string } | null;
  } | null>(null);
  const [isTiktokConnecting, setIsTiktokConnecting] = useState(false);
  const [tiktokMessage, setTiktokMessage] = useState<string | null>(null);
  const { data: session, isPending } = useSession();
  const isAdmin = Boolean((session?.user as { is_admin?: boolean } | undefined)?.is_admin);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeProfileId, setActiveProfileIdState] = useState<string | null>(null);
  const [channelsError, setChannelsError] = useState<string | null>(null);
  const [renamingProfileId, setRenamingProfileId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [channelBusy, setChannelBusy] = useState<string | null>(null);

  const paidPlans = getPublicBillingPlans();

  // Load available fonts from backend and inject them into the page
  useEffect(() => {
    const loadFonts = async () => {
      try {
        const response = await fetch('/api/fonts', { cache: 'no-store' });
        if (response.ok) {
          const data = await response.json();
          setAvailableFonts(data.fonts || []);

          // Dynamically load fonts using @font-face
          const fontFaceStyles = data.fonts.map((font: { name: string }) => {
            return `
              @font-face {
                font-family: '${font.name}';
                src: url('/api/fonts/${font.name}') format('truetype');
                font-weight: normal;
                font-style: normal;
              }
            `;
          }).join('\n');

          // Inject font styles into the page
          const styleElement = document.createElement('style');
          styleElement.id = 'custom-fonts';
          styleElement.innerHTML = fontFaceStyles;

          // Remove existing custom fonts style if present
          const existingStyle = document.getElementById('custom-fonts');
          if (existingStyle) {
            existingStyle.remove();
          }

          document.head.appendChild(styleElement);
        }
      } catch (error) {
        console.error('Failed to load fonts:', error);
      }
    };

    loadFonts();
  }, []);

  // Load user preferences
  useEffect(() => {
    const loadPreferences = async () => {
      if (!session?.user?.id) return;

      setIsFetching(true);
      try {
        const response = await fetch('/api/preferences');
        if (response.ok) {
          const data: UserPreferences = await response.json();
          setFontFamily(data.fontFamily);
          setFontSize(data.fontSize);
          setFontColor(data.fontColor);
          setCompletionEmails(data.notifyOnCompletion ?? true);
        }
      } catch (error) {
        console.error('Failed to load preferences:', error);
      } finally {
        setIsFetching(false);
      }
    };

    loadPreferences();
  }, [session?.user?.id]);

  // Load YouTube publishing status
  useEffect(() => {
    const loadYoutubeStatus = async () => {
      try {
        const response = await fetch("/api/publish/status");
        if (response.ok) {
          const data = await response.json();
          setYoutubeStatus({
            configured: data.youtube_configured ?? false,
            channel: data.channel ?? null,
          });
          setTiktokStatus({
            configured: data.tiktok_configured ?? false,
            user: data.tiktok_user ?? null,
          });
        }
      } catch (error) {
        console.error("Failed to load publishing status:", error);
      }
    };

    loadYoutubeStatus();
  }, []);

  // Load publishing channels
  useEffect(() => {
    const loadProfiles = async () => {
      try {
        const data = await fetchProfiles();
        setProfiles(data.profiles);
        setActiveProfileIdState(data.active_profile_id);
      } catch (error) {
        console.error("Failed to load publishing channels:", error);
      }
    };

    loadProfiles();
  }, []);

  const refreshProfiles = async () => {
    const data = await fetchProfiles();
    setProfiles(data.profiles);
    setActiveProfileIdState(data.active_profile_id);
  };

  const handleRenameProfile = async (profileId: string) => {
    const name = renameValue.trim();
    if (!name || channelBusy) return;
    setChannelBusy(`rename-${profileId}`);
    setChannelsError(null);
    try {
      await renameProfile(profileId, name);
      setRenamingProfileId(null);
      setRenameValue("");
      await refreshProfiles();
    } catch (error) {
      setChannelsError(
        error instanceof Error ? error.message : "Failed to rename channel"
      );
    } finally {
      setChannelBusy(null);
    }
  };

  const handleDisconnectAccount = async (
    profileId: string,
    platform: "youtube" | "tiktok",
  ) => {
    if (channelBusy) return;
    setChannelBusy(`disconnect-${profileId}-${platform}`);
    setChannelsError(null);
    try {
      await disconnectAccount(profileId, platform);
      await refreshProfiles();
    } catch (error) {
      setChannelsError(
        error instanceof Error ? error.message : "Failed to disconnect account"
      );
    } finally {
      setChannelBusy(null);
    }
  };

  const handleDeleteProfile = async (profileId: string) => {
    if (channelBusy) return;
    setChannelBusy(`delete-${profileId}`);
    setChannelsError(null);
    try {
      await deleteProfile(profileId);
      await refreshProfiles();
    } catch (error) {
      setChannelsError(
        error instanceof Error ? error.message : "Failed to delete channel"
      );
    } finally {
      setChannelBusy(null);
    }
  };

  useEffect(() => {
    const fetchBillingSummary = async () => {
      if (!session?.user?.id) return;

      try {
        const response = await fetch("/api/tasks/billing-summary", {
          cache: "no-store",
        });

        if (!response.ok) {
          return;
        }

        const data: BillingSummary = await response.json();
        setBillingSummary(data);
      } catch (fetchError) {
        console.error("Failed to fetch billing summary:", fetchError);
      }
    };

    fetchBillingSummary();
  }, [session?.user?.id]);

  const handleBillingAction = async (selectedPlan?: BillingPlanId) => {
    if (!billingSummary?.monetization_enabled) return;

    const isPaid = isPaidBillingPlan(billingSummary.plan);
    const route = isPaid ? "/api/billing/portal" : "/api/billing/checkout";
    const body = !isPaid && selectedPlan ? JSON.stringify({ plan: selectedPlan }) : undefined;

    try {
      setIsBillingActionLoading(true);
      const response = await fetch(route, {
        method: "POST",
        ...(body
          ? {
              headers: { "Content-Type": "application/json" },
              body,
            }
          : {}),
      });
      const responseText = await response.text();
      let data: { url?: string; error?: string } = {};
      if (responseText) {
        try {
          data = JSON.parse(responseText);
        } catch {
          data = { error: responseText };
        }
      }

      if (!response.ok || !data.url) {
        throw new Error(data.error || "Unable to open billing");
      }

      track(isPaid ? "billing_portal_opened" : "billing_checkout_started", {
        plan: billingSummary.plan,
        selected_plan: selectedPlan,
      });
      window.location.href = data.url;
    } catch (billingError) {
      setError(billingError instanceof Error ? billingError.message : "Billing action failed");
    } finally {
      setIsBillingActionLoading(false);
    }
  };

  const handleConnectYouTube = async () => {
    setIsYoutubeConnecting(true);
    setYoutubeMessage(null);
    try {
      const response = await fetch("/api/publish/youtube/auth-url");
      const data = await response.json();
      if (!response.ok || !data.url) {
        throw new Error(data.detail || "YouTube is not configured. Set YOUTUBE_CLIENT_ID first.");
      }
      window.location.href = data.url;
    } catch (youtubeError) {
      setYoutubeMessage(
        youtubeError instanceof Error ? youtubeError.message : "Failed to connect YouTube"
      );
      setIsYoutubeConnecting(false);
    }
  };

  const handleConnectTikTok = async () => {
    setIsTiktokConnecting(true);
    setTiktokMessage(null);
    try {
      const response = await fetch("/api/publish/tiktok/auth-url");
      const data = await response.json();
      if (!response.ok || !data.url) {
        throw new Error(data.detail || "TikTok is not configured. Set TIKTOK_CLIENT_KEY first.");
      }
      window.location.href = data.url;
    } catch (tiktokError) {
      setTiktokMessage(
        tiktokError instanceof Error ? tiktokError.message : "Failed to connect TikTok"
      );
      setIsTiktokConnecting(false);
    }
  };

  const handleSavePreferences = async () => {
    setIsLoading(true);
    setError(null);
    setSuccess(false);

    try {
      const response = await fetch('/api/preferences', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          fontFamily,
          fontSize,
          fontColor,
          notifyOnCompletion: completionEmails,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to save preferences');
      }

      track("preferences_saved");
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (error) {
      console.error('Error saving preferences:', error);
      setError(error instanceof Error ? error.message : 'Failed to save preferences');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignOut = async () => {
    await signOut();
    window.location.href = "/sign-in";
  };

  const activeProfileName =
    profiles.find((profile) => profile.id === activeProfileId)?.name ?? null;

  if (isPending || isFetching) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center p-4">
        <div className="space-y-4">
          <Skeleton className="h-4 w-32 mx-auto" />
          <Skeleton className="h-4 w-48 mx-auto" />
          <Skeleton className="h-4 w-24 mx-auto" />
        </div>
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className="min-h-screen bg-white">
        <div className="max-w-4xl mx-auto px-4 py-24">
          <div className="text-center">
            <h1 className="text-3xl font-bold text-black mb-4">
              Sign In Required
            </h1>
            <p className="text-gray-600 mb-8">
              You need to sign in to access your settings
            </p>
            <Link href="/sign-in">
              <Button size="lg">Sign In</Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="border-b bg-white">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex justify-between items-center">
            <Link href="/">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="w-4 h-4" />
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
              <Button variant="outline" size="sm" onClick={handleSignOut}>
                Sign Out
              </Button>
              <ProfileSwitcher />
              <Avatar className="w-8 h-8">
                <AvatarImage src={session.user.image || ""} />
                <AvatarFallback className="bg-gray-100 text-black text-sm">
                  {session.user.name?.charAt(0) || session.user.email?.charAt(0) || "U"}
                </AvatarFallback>
              </Avatar>
              <div className="hidden sm:block">
                <p className="text-sm font-medium text-black">{session.user.name}</p>
                <p className="text-xs text-gray-500">{session.user.email}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="max-w-xl mx-auto">
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-2">
              <Settings className="w-6 h-6 text-black" />
              <h2 className="text-2xl font-bold text-black">
                Settings
              </h2>
            </div>
            <p className="text-gray-600">
              Configure your default preferences for video clip generation
            </p>
          </div>

          <Separator className="my-8" />

          <div className="space-y-8">
            {/* Font Preferences Section */}
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-black mb-1">
                  Default Font Settings
                </h3>
                <p className="text-sm text-gray-600">
                  These settings will be applied to all new video processing tasks
                </p>
              </div>

              {/* Font Family Selector */}
              <div className="space-y-2">
                <Label className="text-sm font-medium text-black flex items-center gap-2">
                  <Type className="w-4 h-4" />
                  Font Family
                </Label>
                <Select value={fontFamily} onValueChange={setFontFamily} disabled={isLoading}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select font" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableFonts.map((font) => (
                      <SelectItem key={font.name} value={font.name}>
                        {font.display_name}
                      </SelectItem>
                    ))}
                    {availableFonts.length === 0 && (
                      <SelectItem value="TikTokSans-Regular">TikTok Sans Regular</SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>

              {/* Font Size Slider */}
              <div className="space-y-2">
                <Label className="text-sm font-medium text-black">
                  Font Size: {fontSize}px
                </Label>
                <div className="px-2">
                  <Slider
                    value={[fontSize]}
                    onValueChange={(value) => setFontSize(value[0])}
                    max={48}
                    min={12}
                    step={2}
                    disabled={isLoading}
                    className="w-full"
                  />
                </div>
                <div className="flex justify-between text-xs text-gray-500">
                  <span>12px</span>
                  <span>48px</span>
                </div>
              </div>

              {/* Font Color Picker */}
              <div className="space-y-2">
                <Label className="text-sm font-medium text-black flex items-center gap-2">
                  <Palette className="w-4 h-4" />
                  Font Color
                </Label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={fontColor}
                    onChange={(e) => setFontColor(e.target.value)}
                    disabled={isLoading}
                    className="w-12 h-10 rounded border border-gray-300 cursor-pointer disabled:cursor-not-allowed"
                  />
                  <Input
                    type="text"
                    value={fontColor}
                    onChange={(e) => setFontColor(e.target.value)}
                    disabled={isLoading}
                    placeholder="#FFFFFF"
                    className="flex-1 h-10"
                    pattern="^#[0-9A-Fa-f]{6}$"
                  />
                </div>
                <div className="flex gap-2 mt-2">
                  {["#FFFFFF", "#000000", "#FFD700", "#FF6B6B", "#4ECDC4", "#45B7D1"].map((color) => (
                    <button
                      key={color}
                      type="button"
                      onClick={() => setFontColor(color)}
                      disabled={isLoading}
                      className="w-8 h-8 rounded border-2 border-gray-300 cursor-pointer hover:scale-110 transition-transform disabled:cursor-not-allowed"
                      style={{ backgroundColor: color }}
                      title={color}
                    />
                  ))}
                </div>
              </div>

              {/* Preview */}
              <div className="space-y-2">
                <Label className="text-sm font-medium text-black">Preview</Label>
                <div className="p-6 bg-black rounded-lg flex items-center justify-center min-h-[100px]">
                  <p
                    style={{
                      color: fontColor,
                      fontSize: `${Math.min(fontSize, 32)}px`,
                      fontFamily: `'${fontFamily}', system-ui, -apple-system, sans-serif`,
                      textAlign: 'center',
                      lineHeight: '1.4'
                    }}
                    className="font-medium"
                  >
                    Your subtitle will look like this
                  </p>
                </div>
              </div>
            </div>

            {/* Notifications Section */}
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-black mb-1">
                  Notifications
                </h3>
                <p className="text-sm text-gray-600">
                  Manage how you receive updates about your clips
                </p>
              </div>

              <div className="flex items-center justify-between">
                <Label htmlFor="completion-emails" className="flex items-center gap-2 text-sm font-medium text-black cursor-pointer">
                  <Mail className="w-4 h-4" />
                  Completion emails
                  <span className="text-gray-500 font-normal">— get notified when clips are ready</span>
                </Label>
                <Switch
                  id="completion-emails"
                  checked={completionEmails}
                  onCheckedChange={setCompletionEmails}
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Developer Section */}
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-black mb-1">
                  Developer
                </h3>
                <p className="text-sm text-gray-600">
                  Programmatic access for tools like the SupoClip MCP server
                </p>
              </div>

              <Link href="/settings/api-keys" className="block">
                <div className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 transition-colors">
                  <div className="flex items-center gap-3">
                    <KeyRound className="w-5 h-5 text-black" />
                    <div>
                      <p className="text-sm font-medium text-black">API Keys</p>
                      <p className="text-xs text-gray-500">Create and manage API keys</p>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                </div>
              </Link>
            </div>

            {/* Publishing Channels Section */}
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-black mb-1">
                  Publishing Channels
                </h3>
                <p className="text-sm text-gray-600">
                  Each channel owns its own YouTube and TikTok accounts. Use the channel switcher in the top bar to select which channel to publish to.
                </p>
              </div>

              <div className="space-y-3">
                {profiles.map((profile) => (
                  <div key={profile.id} className="border rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        {renamingProfileId === profile.id ? (
                          <Input
                            value={renameValue}
                            onChange={(event) => setRenameValue(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") void handleRenameProfile(profile.id);
                              if (event.key === "Escape") setRenamingProfileId(null);
                            }}
                            autoFocus
                            className="h-8 w-48 text-sm"
                          />
                        ) : (
                          <p className="text-sm font-medium text-black truncate">
                            {profile.name}
                          </p>
                        )}
                        {profile.is_default && (
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5">
                            Default
                          </Badge>
                        )}
                        {profile.id === activeProfileId && (
                          <Badge className="text-[10px] px-1.5 py-0 h-5 bg-stone-900 text-white">
                            Active
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {renamingProfileId === profile.id ? (
                          <Button
                            size="sm"
                            className="h-7 px-2 text-xs"
                            onClick={() => void handleRenameProfile(profile.id)}
                            disabled={channelBusy !== null || !renameValue.trim()}
                          >
                            {channelBusy === `rename-${profile.id}` ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              "Save"
                            )}
                          </Button>
                        ) : (
                          <>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 px-2"
                              onClick={() => {
                                setRenamingProfileId(profile.id);
                                setRenameValue(profile.name);
                              }}
                              disabled={channelBusy !== null}
                              aria-label={`Rename ${profile.name}`}
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </Button>
                            {!profile.is_default && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 px-2 text-red-600 hover:text-red-700"
                                onClick={() => void handleDeleteProfile(profile.id)}
                                disabled={channelBusy !== null}
                                aria-label={`Delete ${profile.name}`}
                              >
                                {channelBusy === `delete-${profile.id}` ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <Trash2 className="w-3.5 h-3.5" />
                                )}
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    </div>

                    <div className="grid gap-2 sm:grid-cols-2">
                      <div className="flex items-center justify-between gap-2 rounded-lg bg-gray-50 border border-gray-100 px-3 py-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <Youtube className="w-4 h-4 text-red-500 flex-shrink-0" />
                          {profile.accounts.youtube.connected ? (
                            <div className="min-w-0">
                              <p className="text-xs font-medium text-black truncate">
                                {profile.accounts.youtube.title ?? "YouTube"}
                              </p>
                              {profile.accounts.youtube.handle && (
                                <p className="text-[10px] text-gray-500 truncate">
                                  @{profile.accounts.youtube.handle}
                                </p>
                              )}
                            </div>
                          ) : (
                            <span className="text-xs text-gray-500">Not connected</span>
                          )}
                        </div>
                        {profile.accounts.youtube.connected && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-6 px-1.5 text-gray-500 hover:text-red-600"
                            onClick={() => void handleDisconnectAccount(profile.id, "youtube")}
                            disabled={channelBusy !== null}
                            aria-label={`Disconnect YouTube for ${profile.name}`}
                          >
                            {channelBusy === `disconnect-${profile.id}-youtube` ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <Unlink className="w-3 h-3" />
                            )}
                          </Button>
                        )}
                      </div>

                      <div className="flex items-center justify-between gap-2 rounded-lg bg-gray-50 border border-gray-100 px-3 py-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <Music2 className="w-4 h-4 text-gray-500 flex-shrink-0" />
                          {profile.accounts.tiktok.connected ? (
                            <div className="min-w-0">
                              <p className="text-xs font-medium text-black truncate">
                                {profile.accounts.tiktok.display_name ?? "TikTok"}
                              </p>
                            </div>
                          ) : (
                            <span className="text-xs text-gray-500">Not connected</span>
                          )}
                        </div>
                        {profile.accounts.tiktok.connected && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-6 px-1.5 text-gray-500 hover:text-red-600"
                            onClick={() => void handleDisconnectAccount(profile.id, "tiktok")}
                            disabled={channelBusy !== null}
                            aria-label={`Disconnect TikTok for ${profile.name}`}
                          >
                            {channelBusy === `disconnect-${profile.id}-tiktok` ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <Unlink className="w-3 h-3" />
                            )}
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
                {profiles.length === 0 && (
                  <p className="text-sm text-gray-500">
                    No publishing channels yet. Create one with the channel switcher.
                  </p>
                )}
              </div>

              {channelsError && (
                <Alert className="border-red-200 bg-red-50">
                  <AlertCircle className="h-4 w-4 text-red-500" />
                  <AlertDescription className="text-sm text-red-700">
                    {channelsError}
                  </AlertDescription>
                </Alert>
              )}
            </div>

            {/* YouTube Publishing Section */}
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-black mb-1">
                  YouTube Publishing
                </h3>
                <p className="text-sm text-gray-600">
                  Auto-publish generated clips to YouTube at their scheduled time.
                </p>
                {activeProfileName && (
                  <p className="text-xs text-gray-500 mt-1">
                    Applies to active channel: <span className="font-medium text-black">{activeProfileName}</span>
                  </p>
                )}
              </div>

              <div className="flex items-start justify-between gap-4 p-4 border rounded-lg">
                <div className="flex items-center gap-3">
                  {youtubeStatus?.configured ? (
                    <CheckCircle className="w-5 h-5 text-green-500" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-gray-400" />
                  )}
                  <div>
                    <p className="text-sm font-medium text-black">
                      {youtubeStatus?.configured
                        ? `Connected: ${youtubeStatus.channel?.title ?? youtubeStatus.channel?.handle ?? "YouTube channel"}`
                        : "Not connected"}
                    </p>
                    <p className="text-xs text-gray-500">
                      {youtubeStatus?.configured
                        ? "New clips will be uploaded directly to YouTube."
                        : "Connect your channel to publish clips directly (free, no monthly cap)."}
                    </p>
                  </div>
                </div>
                <Button
                  type="button"
                  variant={youtubeStatus?.configured ? "outline" : "default"}
                  onClick={handleConnectYouTube}
                  disabled={isYoutubeConnecting}
                >
                  {isYoutubeConnecting
                    ? "Redirecting..."
                    : youtubeStatus?.configured
                    ? "Reconnect"
                    : "Connect YouTube"}
                </Button>
              </div>

              {youtubeMessage && (
                <Alert className="border-red-200 bg-red-50">
                  <AlertCircle className="h-4 w-4 text-red-500" />
                  <AlertDescription className="text-sm text-red-700">
                    {youtubeMessage}
                  </AlertDescription>
                </Alert>
              )}
            </div>

            {/* TikTok Publishing Section */}
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-black mb-1">
                  TikTok Publishing
                </h3>
                <p className="text-sm text-gray-600">
                  Schedule and auto-publish generated clips to your TikTok account.
                </p>
                {activeProfileName && (
                  <p className="text-xs text-gray-500 mt-1">
                    Applies to active channel: <span className="font-medium text-black">{activeProfileName}</span>
                  </p>
                )}
              </div>

              <div className="flex items-start justify-between gap-4 p-4 border rounded-lg">
                <div className="flex items-center gap-3">
                  {tiktokStatus?.configured ? (
                    <CheckCircle className="w-5 h-5 text-green-500" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-gray-400" />
                  )}
                  <div>
                    <p className="text-sm font-medium text-black">
                      {tiktokStatus?.configured
                        ? `Connected: ${tiktokStatus.user?.display_name ?? "TikTok account"}`
                        : "Not connected"}
                    </p>
                    <p className="text-xs text-gray-500">
                      {tiktokStatus?.configured
                        ? "Clips can be scheduled and published to TikTok automatically."
                        : "Connect your TikTok account to schedule clips. Requires the video.upload scope and Direct Post (video.publish) for auto-publishing."}
                    </p>
                  </div>
                </div>
                <Button
                  type="button"
                  variant={tiktokStatus?.configured ? "outline" : "default"}
                  onClick={handleConnectTikTok}
                  disabled={isTiktokConnecting}
                >
                  {isTiktokConnecting
                    ? "Redirecting..."
                    : tiktokStatus?.configured
                    ? "Reconnect"
                    : "Connect TikTok"}
                </Button>
              </div>

              {tiktokMessage && (
                <Alert className="border-red-200 bg-red-50">
                  <AlertCircle className="h-4 w-4 text-red-500" />
                  <AlertDescription className="text-sm text-red-700">
                    {tiktokMessage}
                  </AlertDescription>
                </Alert>
              )}
            </div>

            <Separator className="mb-4" />

            {/* Success/Error Messages */}
            {success && (
              <Alert className="border-green-200 bg-green-50">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <AlertDescription className="text-sm text-green-700">
                  Preferences saved successfully!
                </AlertDescription>
              </Alert>
            )}

            {error && (
              <Alert className="border-red-200 bg-red-50">
                <AlertCircle className="h-4 w-4 text-red-500" />
                <AlertDescription className="text-sm text-red-700">
                  {error}
                </AlertDescription>
              </Alert>
            )}

            {/* Save Button */}
            {billingSummary?.monetization_enabled && (
              <div className="border rounded-lg p-4 bg-gray-50 space-y-3">
                <div>
                  <h3 className="text-lg font-semibold text-black">Billing</h3>
                  {!isPaidBillingPlan(billingSummary.plan) && (
                    <p className="text-sm text-gray-600">Video processing requires a paid plan.</p>
                  )}
                  <p className="text-sm text-gray-600">
                    {billingSummary.upgrade_required
                      ? "Current plan cannot create generations."
                      : billingSummary.usage_limit === null
                      ? `${billingSummary.usage_count} generations in this billing period`
                      : `${billingSummary.usage_count}/${billingSummary.usage_limit} generations used this period`}
                  </p>
                  <p className="text-sm text-gray-500">
                    Plan: {formatBillingPlanName(billingSummary.plan)} ({billingSummary.subscription_status})
                  </p>
                </div>

                {isPaidBillingPlan(billingSummary.plan) ? (
                  billingSummary.subscription_provider === "apple" ? (
                    <p className="rounded-md border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600">
                      Managed through the App Store
                    </p>
                  ) : (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => handleBillingAction()}
                      disabled={isBillingActionLoading}
                      className="w-full"
                    >
                      {isBillingActionLoading ? "Loading..." : "Manage Billing"}
                    </Button>
                  )
                ) : (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {paidPlans.map((plan) => (
                      <Button
                        key={plan.id}
                        type="button"
                        variant={plan.highlighted ? "default" : "outline"}
                        onClick={() => handleBillingAction(plan.id)}
                        disabled={isBillingActionLoading}
                        className="h-auto min-h-12 flex-col gap-0.5 py-2"
                      >
                        <span>{isBillingActionLoading ? "Loading..." : plan.cta}</span>
                        <span className="text-xs font-normal opacity-80">
                          ${plan.priceMonthly}/mo · {plan.generationLimit} generations
                        </span>
                      </Button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <Button
              onClick={handleSavePreferences}
              disabled={isLoading}
              className="w-full h-11"
            >
              {isLoading ? "Saving..." : "Save Preferences"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
