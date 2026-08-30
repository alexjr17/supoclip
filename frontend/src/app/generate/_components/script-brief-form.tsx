"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2, Sparkles } from "lucide-react";

import { SCRIPT_DURATIONS, SCRIPT_TONES, type ScriptTone } from "@/lib/scripts";

export interface ScriptBrief {
  idea: string;
  target_duration_seconds: number;
  tone: ScriptTone;
  language: string;
  with_characters: boolean;
}

const LANGUAGES = ["English", "Spanish", "Portuguese", "French", "German", "Italian"];

interface ScriptBriefFormProps {
  brief: ScriptBrief;
  onChange: (brief: ScriptBrief) => void;
  onSubmit: () => void;
  isGenerating: boolean;
}

export function ScriptBriefForm({
  brief,
  onChange,
  onSubmit,
  isGenerating,
}: ScriptBriefFormProps) {
  const update = <K extends keyof ScriptBrief>(key: K, value: ScriptBrief[K]) =>
    onChange({ ...brief, [key]: value });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-black">
          <Sparkles className="h-4 w-4" />
          The idea
        </CardTitle>
        <CardDescription>
          Describe what the video should be about. The more specific, the better the script.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="idea" className="text-sm font-medium text-black">
            Idea
          </Label>
          <Textarea
            id="idea"
            value={brief.idea}
            onChange={(event) => update("idea", event.target.value)}
            disabled={isGenerating}
            rows={4}
            placeholder="e.g. Three habits that quietly ruin your sleep, and what to do instead"
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-2">
            <Label className="text-sm font-medium text-black">Length</Label>
            <Select
              value={String(brief.target_duration_seconds)}
              onValueChange={(value) => update("target_duration_seconds", Number(value))}
              disabled={isGenerating}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SCRIPT_DURATIONS.map((seconds) => (
                  <SelectItem key={seconds} value={String(seconds)}>
                    {seconds}s
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label className="text-sm font-medium text-black">Tone</Label>
            <Select
              value={brief.tone}
              onValueChange={(value) => update("tone", value as ScriptTone)}
              disabled={isGenerating}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SCRIPT_TONES.map((tone) => (
                  <SelectItem key={tone.value} value={tone.value}>
                    {tone.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label className="text-sm font-medium text-black">Language</Label>
            <Select
              value={brief.language}
              onValueChange={(value) => update("language", value)}
              disabled={isGenerating}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LANGUAGES.map((language) => (
                  <SelectItem key={language} value={language}>
                    {language}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex items-start justify-between gap-4 rounded-lg border p-4">
          <div>
            <Label
              htmlFor="with-characters"
              className="cursor-pointer text-sm font-medium text-black"
            >
              Use a recurring cast
            </Label>
            <p className="mt-1 text-xs text-gray-500">
              Adds named characters reused across scenes. Keeps names, roles and tone consistent —
              it cannot make stock footage show the same face twice.
            </p>
          </div>
          <Switch
            id="with-characters"
            checked={brief.with_characters}
            onCheckedChange={(value) => update("with_characters", value)}
            disabled={isGenerating}
          />
        </div>

        <Button
          onClick={onSubmit}
          disabled={isGenerating || brief.idea.trim().length < 3}
          className="h-11 w-full"
        >
          {/*
            Each branch keeps its label inside a <span> rather than as a bare
            text node beside the icon. Page translators (Google Translate)
            replace loose text nodes with their own <font> wrappers; when React
            then swaps these children it holds a reference to a node that is no
            longer a child of the button, and insertBefore throws NotFoundError.
            Swapping elements instead of text nodes keeps that safe.
          */}
          {isGenerating ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Writing the script...</span>
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" />
              <span>Generate script</span>
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}
