import type { SupportedModelInfo } from './types';

export const DEFAULT_MODEL_ID = 'gemini-3.6-flash';

const LEGACY_MODEL_UPGRADES: Record<string, string> = {
  'gemini-2.5-flash': 'gemini-3.6-flash',
  'gemini-2.5-pro': 'gemini-3.8-flash',
  'gemini-2.5-flash-lite': 'gemini-3.5-flash-lite',
  'gemini-2.0-flash': 'gemini-3.5-flash-lite',
};

export function resolveActiveModelId(modelId: string | null | undefined): string {
  const cleaned = (modelId || '').trim();
  if (!cleaned) return '';
  return LEGACY_MODEL_UPGRADES[cleaned.toLowerCase()] || cleaned;
}

export const DEFAULT_MODELS: SupportedModelInfo[] = [
  {
    id: 'gpt-4o-mini',
    label: 'ChatGPT (GPT-4o mini)',
    provider: 'openai',
    tier: 'Fast & Popular',
    description: 'Reliable everyday ChatGPT writer with crisp structure and smooth flow.',
    configured: false,
  },
  {
    id: 'gpt-4o',
    label: 'ChatGPT (GPT-4o)',
    provider: 'openai',
    tier: 'Flagship OpenAI',
    description: 'High-craft ChatGPT model for nuanced hooks and long-form storytelling.',
    configured: false,
  },
  {
    id: 'openai/gpt-oss-120b',
    label: 'GPT-OSS 120B (Groq)',
    provider: 'groq',
    tier: 'Ultra Fast',
    description: 'Very fast open AI on Groq — great high-speed free-tier writer outside Google.',
    configured: false,
  },
  {
    id: 'openai/gpt-4o-mini',
    label: 'GPT-4o mini (OpenRouter)',
    provider: 'openrouter',
    tier: 'Multi-AI Hub',
    description: 'Run ChatGPT and dozens of AI models using a single OpenRouter key.',
    configured: false,
  },
  {
    id: 'gemini-3.6-flash',
    label: 'Gemini 3.6 Flash',
    provider: 'gemini',
    tier: 'Everyday Gemini',
    description: 'Google Gemini writer with automatic backup if Google servers get busy.',
    configured: false,
  },
  {
    id: 'gemini-3.5-flash',
    label: 'Gemini 3.5 Flash',
    provider: 'gemini',
    tier: 'Steady Gemini',
    description: 'Reliable Google Gemini model with lower traffic congestion.',
    configured: false,
  },
];

const PREFERRED_MODEL_KEY = 'veridra_preferred_model';

export function getSavedPreferredModel(): string {
  try {
    const raw = window.localStorage.getItem(PREFERRED_MODEL_KEY) || '';
    const upgraded = resolveActiveModelId(raw);
    if (upgraded && upgraded !== raw) {
      window.localStorage.setItem(PREFERRED_MODEL_KEY, upgraded);
    }
    return upgraded;
  } catch {
    return '';
  }
}

export function savePreferredModel(modelId: string): void {
  try {
    const resolved = resolveActiveModelId(modelId);
    if (resolved) {
      window.localStorage.setItem(PREFERRED_MODEL_KEY, resolved);
    } else {
      window.localStorage.removeItem(PREFERRED_MODEL_KEY);
    }
  } catch {
    // Ignore storage error
  }
}
