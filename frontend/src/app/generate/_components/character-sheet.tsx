"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Users } from "lucide-react";

import type { ScriptCharacter } from "@/lib/scripts";

interface CharacterSheetProps {
  characters: ScriptCharacter[];
  onChange: (characters: ScriptCharacter[]) => void;
}

/**
 * The cast the scenes refer to.
 *
 * With a stock-footage pipeline this sheet cannot pin down a face — stock
 * libraries return a different person for every query. What it does hold is
 * the things that *can* stay consistent: the name, the role, the tone of the
 * narration, and the exact search terms reused on every appearance.
 */
export function CharacterSheet({ characters, onChange }: CharacterSheetProps) {
  if (characters.length === 0) {
    return null;
  }

  const updateAt = (index: number, character: ScriptCharacter) =>
    onChange(characters.map((existing, i) => (i === index ? character : existing)));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-semibold text-black">
          <Users className="h-4 w-4" />
          Cast
        </CardTitle>
        <CardDescription>
          Keeps names, roles and tone consistent across scenes, and fixes the search terms used
          whenever a character appears. It does not guarantee the same face — stock footage returns
          a different person each time.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {characters.map((character, index) => (
          <div key={`${character.name}-${index}`} className="space-y-3 rounded-lg border p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label className="text-xs font-medium text-gray-600">Name</Label>
                <Input
                  value={character.name}
                  onChange={(event) =>
                    updateAt(index, { ...character, name: event.target.value })
                  }
                  className="h-9 text-sm"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-xs font-medium text-gray-600">Role</Label>
                <Input
                  value={character.role}
                  onChange={(event) =>
                    updateAt(index, { ...character, role: event.target.value })
                  }
                  className="h-9 text-sm"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-medium text-gray-600">Description</Label>
              <Input
                value={character.description}
                onChange={(event) =>
                  updateAt(index, { ...character, description: event.target.value })
                }
                className="h-9 text-sm"
              />
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label className="text-xs font-medium text-gray-600">Voice tone</Label>
                <Input
                  value={character.voice_tone}
                  onChange={(event) =>
                    updateAt(index, { ...character, voice_tone: event.target.value })
                  }
                  className="h-9 text-sm"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-xs font-medium text-gray-600">
                  Stock keywords <span className="font-normal text-gray-400">— English</span>
                </Label>
                <Input
                  value={character.stock_keywords.join(", ")}
                  onChange={(event) =>
                    updateAt(index, {
                      ...character,
                      stock_keywords: event.target.value
                        .split(",")
                        .map((keyword) => keyword.trim())
                        .filter(Boolean),
                    })
                  }
                  className="h-9 text-sm"
                />
              </div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
