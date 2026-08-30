"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Mail, Palette, Type } from "lucide-react";

import { ErrorAlert, SettingsSection, SuccessAlert } from "./settings-section";
import { DEFAULT_FONT_FAMILY, type FontChoice } from "../_hooks/use-clip-defaults";

const COLOR_SWATCHES = ["#FFFFFF", "#000000", "#FFD700", "#FF6B6B", "#4ECDC4", "#45B7D1"];

interface CaptionDefaultsSectionProps {
  fonts: FontChoice[];
  fontFamily: string;
  onFontFamilyChange: (value: string) => void;
  fontSize: number;
  onFontSizeChange: (value: number) => void;
  fontColor: string;
  onFontColorChange: (value: string) => void;
  completionEmails: boolean;
  onCompletionEmailsChange: (value: boolean) => void;
  isSaving: boolean;
  error: string | null;
  success: boolean;
  onSave: () => void;
}

/**
 * The only section on this page backed by a Save button: the four values it
 * shows are persisted together by PATCH /api/preferences. Keeping the button
 * inside the card makes it obvious what it does and does not save — it used to
 * sit at the very bottom of the page, below the publishing and billing
 * sections it has no effect on.
 */
export function CaptionDefaultsSection({
  fonts,
  fontFamily,
  onFontFamilyChange,
  fontSize,
  onFontSizeChange,
  fontColor,
  onFontColorChange,
  completionEmails,
  onCompletionEmailsChange,
  isSaving,
  error,
  success,
  onSave,
}: CaptionDefaultsSectionProps) {
  return (
    <SettingsSection
      id="captions"
      icon={<Type className="h-4 w-4" />}
      title="Caption defaults"
      description="Applied to every new clip you generate. You can still override them per task."
    >
      <div className="grid gap-6 sm:grid-cols-2">
        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Font family</Label>
          <Select value={fontFamily} onValueChange={onFontFamilyChange} disabled={isSaving}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select font" />
            </SelectTrigger>
            <SelectContent>
              {fonts.map((font) => (
                <SelectItem key={font.name} value={font.name}>
                  {font.display_name}
                </SelectItem>
              ))}
              {fonts.length === 0 && (
                <SelectItem value={DEFAULT_FONT_FAMILY}>TikTok Sans Regular</SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label className="flex items-center gap-2 text-sm font-medium text-black">
            <Palette className="h-4 w-4" />
            Colour
          </Label>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={fontColor}
              onChange={(event) => onFontColorChange(event.target.value)}
              disabled={isSaving}
              aria-label="Caption colour"
              className="h-10 w-12 cursor-pointer rounded border border-gray-300 disabled:cursor-not-allowed"
            />
            <Input
              type="text"
              value={fontColor}
              onChange={(event) => onFontColorChange(event.target.value)}
              disabled={isSaving}
              placeholder="#FFFFFF"
              className="h-10 flex-1"
              pattern="^#[0-9A-Fa-f]{6}$"
            />
          </div>
          <div className="flex gap-2 pt-1">
            {COLOR_SWATCHES.map((color) => (
              <button
                key={color}
                type="button"
                onClick={() => onFontColorChange(color)}
                disabled={isSaving}
                className="h-7 w-7 cursor-pointer rounded border-2 border-gray-300 transition-transform hover:scale-110 disabled:cursor-not-allowed"
                style={{ backgroundColor: color }}
                title={color}
                aria-label={`Use ${color}`}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-sm font-medium text-black">Size: {fontSize}px</Label>
        <div className="px-2">
          <Slider
            value={[fontSize]}
            onValueChange={(value) => onFontSizeChange(value[0])}
            max={48}
            min={12}
            step={2}
            disabled={isSaving}
            className="w-full"
          />
        </div>
        <div className="flex justify-between text-xs text-gray-500">
          <span>12px</span>
          <span>48px</span>
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-sm font-medium text-black">Preview</Label>
        <div className="flex min-h-[100px] items-center justify-center rounded-lg bg-black p-6">
          <p
            className="font-medium"
            style={{
              color: fontColor,
              fontSize: `${Math.min(fontSize, 32)}px`,
              fontFamily: `'${fontFamily}', system-ui, -apple-system, sans-serif`,
              textAlign: "center",
              lineHeight: "1.4",
            }}
          >
            Your subtitle will look like this
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between border-t pt-6">
        <Label
          htmlFor="completion-emails"
          className="flex cursor-pointer items-center gap-2 text-sm font-medium text-black"
        >
          <Mail className="h-4 w-4" />
          Completion emails
          <span className="font-normal text-gray-500">— get notified when clips are ready</span>
        </Label>
        <Switch
          id="completion-emails"
          checked={completionEmails}
          onCheckedChange={onCompletionEmailsChange}
          disabled={isSaving}
        />
      </div>

      {success && <SuccessAlert>Preferences saved successfully!</SuccessAlert>}
      {error && <ErrorAlert>{error}</ErrorAlert>}

      <Button onClick={onSave} disabled={isSaving} className="h-11 w-full">
        {isSaving ? "Saving..." : "Save preferences"}
      </Button>
    </SettingsSection>
  );
}
