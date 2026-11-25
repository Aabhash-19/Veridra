import type { DepthType, PlatformType } from './types';

export interface SampleBrief {
  id: string;
  label: string;
  topic: string;
  goal: string;
  platform: PlatformType;
  audience: string;
  tone: string;
  depth: DepthType;
  required_points: string[];
  prohibited_points: string[];
  source_urls: string[];
  call_to_action: string;
}

export const QUICK_START_EXAMPLES: SampleBrief[] = [
  {
    id: 'ex-creator-story',
    label: 'Creator Storytelling',
    topic:
      'Why sharing behind-the-scenes lessons and real mistakes builds stronger trust than polished highlight reels',
    goal: 'Inform and educate the target audience',
    platform: 'linkedin',
    audience: 'Creators, founders, and professionals building online',
    tone: 'warm, authentic',
    depth: 'standard',
    required_points: ['relatable hook', 'one honest takeaway', 'actionable reader tip'],
    prohibited_points: ['exaggerated follower guarantees', 'hype clichés'],
    source_urls: [],
    call_to_action: 'What is one lesson from your week that taught you the most?',
  },
  {
    id: 'ex-thread-habits',
    label: 'Deep Work Habits',
    topic:
      'Practical daily research habits that help writers verify facts quickly without burning out on tabs',
    goal: 'Explain a concept clearly',
    platform: 'x',
    audience: 'Writers, newsletter authors, and solo creators',
    tone: 'crisp, conversational',
    depth: 'standard',
    required_points: ['trustworthy primary links', 'saving sources while reading'],
    prohibited_points: ['fake productivity statistics'],
    source_urls: [],
    call_to_action: 'Which habit keeps your writing workflow calm and grounded?',
  },
  {
    id: 'ex-ig-sleep',
    label: 'Everyday Science',
    topic:
      'How morning sunlight and consistent wake times help reset your natural energy rhythm',
    goal: 'Inform and educate the target audience',
    platform: 'instagram',
    audience: 'Busy creators and everyday readers looking for better routines',
    tone: 'friendly, clear',
    depth: 'concise',
    required_points: ['morning outdoor light exposure', 'consistent wake schedule'],
    prohibited_points: ['medical cures or extreme promises'],
    source_urls: [],
    call_to_action: 'Save this post for your Monday morning reset.',
  },
];
