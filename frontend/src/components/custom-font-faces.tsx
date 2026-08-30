"use client";

export interface CustomFontFace {
  name: string;
  /** File extension reported by /api/fonts ("ttf" | "otf"). */
  format?: string;
}

/**
 * Builds the @font-face block for the fonts served by /api/fonts/{name}.
 *
 * `.otf` files must be declared as `opentype`; declaring them as `truetype`
 * makes some browsers reject the face and silently fall back to a system font.
 */
export function buildFontFaceCss(fonts: CustomFontFace[]): string {
  return fonts
    .map((font) => {
      const format = font.format === "otf" ? "opentype" : "truetype";
      return `
        @font-face {
          font-family: '${font.name}';
          src: url('/api/fonts/${encodeURIComponent(font.name)}') format('${format}');
          font-weight: normal;
          font-style: normal;
        }
      `;
    })
    .join("\n");
}

/**
 * Declares the user's custom fonts as a React-owned <style> element.
 *
 * This used to be done imperatively with `document.head.appendChild()` plus a
 * `getElementById('custom-fonts').remove()`. Mutating <head> behind React's
 * back desynchronises its view of that subtree — React also renders route
 * metadata there — and a later reconciliation throws
 * "NotFoundError: Failed to execute 'removeChild' on 'Node'".
 *
 * Rendering the tag instead lets React insert and remove it itself, so the
 * node is always where React expects it to be.
 */
export function CustomFontFaces({ fonts }: { fonts: CustomFontFace[] }) {
  if (fonts.length === 0) {
    return null;
  }

  return <style dangerouslySetInnerHTML={{ __html: buildFontFaceCss(fonts) }} />;
}