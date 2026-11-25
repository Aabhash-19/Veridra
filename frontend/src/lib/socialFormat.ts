import type { PlatformType } from './types';

function mapChars(text: string, upperBase: number, lowerBase: number, digitBase?: number): string {
  let out = '';
  for (const ch of text) {
    const code = ch.charCodeAt(0);
    if (code >= 65 && code <= 90) {
      out += String.fromCodePoint(upperBase + (code - 65));
    } else if (code >= 97 && code <= 122) {
      out += String.fromCodePoint(lowerBase + (code - 97));
    } else if (digitBase !== undefined && code >= 48 && code <= 57) {
      out += String.fromCodePoint(digitBase + (code - 48));
    } else {
      out += ch;
    }
  }
  return out;
}

export function toUnicodeBold(text: string): string {
  // Mathematical Sans-Serif Bold (renders cleanly on LinkedIn, X, and Instagram)
  return mapChars(text, 0x1d5d4, 0x1d5ee, 0x1d7ec);
}

export function toUnicodeItalic(text: string): string {
  // Mathematical Sans-Serif Italic
  return mapChars(text, 0x1d608, 0x1d622);
}

export function formatForSocialPlatform(
  markdown: string,
  options: { includeSources?: boolean } = {},
): string {
  const { includeSources = true } = options;
  let text = markdown.replace(/\r\n/g, '\n');

  if (!includeSources) {
    const srcIdx = text.search(/\n#{1,3}\s*Sources\b/i);
    if (srcIdx !== -1) {
      text = text.slice(0, srcIdx).trimEnd();
    }
  }

  const lines = text.split('\n').map((line) => {
    const trimmed = line.trim();

    // Markdown headings -> clean bold section headers
    const headingMatch = trimmed.match(/^#{1,4}\s+(.+)$/);
    if (headingMatch) {
      const inner = headingMatch[1].replace(/\*\*(.+?)\*\*/g, '$1').trim();
      return toUnicodeBold(inner);
    }

    // Bullet lists (- or *) -> crisp bullet character
    let updated = line.replace(/^(\s*)[-*]\s+/, '$1• ');

    // Markdown links [label](url) -> "label (url)" unless label already equals url
    updated = updated.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_m, label: string, url: string) =>
      label.trim() === url.trim() ? url : `${label} (${url})`,
    );

    // Bold (**text** or __text__)
    updated = updated.replace(/\*\*([^*\n]+?)\*\*/g, (_m, inner: string) => toUnicodeBold(inner));
    updated = updated.replace(/__([^_\n]+?)__/g, (_m, inner: string) => toUnicodeBold(inner));

    // Italic (*text* or _text_) — avoid breaking URLs or bullet markers
    updated = updated.replace(/(^|[\s(>])\*([^*\n]+?)\*(?=[\s.,!?;:)<]|$)/g, (_m, pre: string, inner: string) =>
      `${pre}${toUnicodeItalic(inner)}`,
    );
    updated = updated.replace(/(^|[\s(>])_([^_\n]+?)_(?=[\s.,!?;:)<]|$)/g, (_m, pre: string, inner: string) =>
      `${pre}${toUnicodeItalic(inner)}`,
    );

    return updated;
  });

  return lines
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function buildComposerUrl(platform: PlatformType, socialText: string): string {
  if (platform === 'linkedin') {
    return `https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(socialText.slice(0, 2900))}`;
  }
  if (platform === 'x') {
    return `https://x.com/intent/post?text=${encodeURIComponent(socialText.slice(0, 280))}`;
  }
  return 'https://www.instagram.com/';
}
