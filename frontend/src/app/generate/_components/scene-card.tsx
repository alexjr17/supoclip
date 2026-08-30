"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ChevronDown, ChevronUp, Trash2 } from "lucide-react";

import type { ScriptScene } from "@/lib/scripts";

interface SceneCardProps {
  scene: ScriptScene;
  isFirst: boolean;
  isLast: boolean;
  onChange: (scene: ScriptScene) => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
}

export function SceneCard({
  scene,
  isFirst,
  isLast,
  onChange,
  onMove,
  onRemove,
}: SceneCardProps) {
  const update = <K extends keyof ScriptScene>(key: K, value: ScriptScene[K]) =>
    onChange({ ...scene, [key]: value });

  return (
    <div className="space-y-3 rounded-lg border bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
            Scene {scene.order}
          </Badge>
          {scene.character_names.map((name) => (
            <Badge key={name} className="h-5 bg-stone-900 px-1.5 text-[10px] text-white">
              {name}
            </Badge>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2"
            onClick={() => onMove(-1)}
            disabled={isFirst}
            aria-label={`Move scene ${scene.order} up`}
          >
            <ChevronUp className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2"
            onClick={() => onMove(1)}
            disabled={isLast}
            aria-label={`Move scene ${scene.order} down`}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-red-600 hover:text-red-700"
            onClick={onRemove}
            aria-label={`Delete scene ${scene.order}`}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-xs font-medium text-gray-600">Narration</Label>
        <Textarea
          value={scene.narration}
          onChange={(event) => update("narration", event.target.value)}
          rows={2}
          className="text-sm"
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-[100px_minmax(0,1fr)]">
        <div className="space-y-2">
          <Label className="text-xs font-medium text-gray-600">Seconds</Label>
          <Input
            type="number"
            min={2}
            max={15}
            step={0.5}
            value={scene.duration_seconds}
            onChange={(event) => update("duration_seconds", Number(event.target.value))}
            className="h-9 text-sm"
          />
        </div>
        <div className="space-y-2">
          <Label className="text-xs font-medium text-gray-600">On screen</Label>
          <Input
            value={scene.visual_description}
            onChange={(event) => update("visual_description", event.target.value)}
            className="h-9 text-sm"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-xs font-medium text-gray-600">
          Stock keywords{" "}
          <span className="font-normal text-gray-400">— comma separated, English</span>
        </Label>
        <Input
          value={scene.stock_keywords.join(", ")}
          onChange={(event) =>
            update(
              "stock_keywords",
              event.target.value
                .split(",")
                .map((keyword) => keyword.trim())
                .filter(Boolean),
            )
          }
          className="h-9 text-sm"
        />
      </div>
    </div>
  );
}
