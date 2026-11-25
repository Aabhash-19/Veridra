import { Fragment, type ReactNode } from 'react';

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const tokenRegex =
    /(\*\*[^*\n]+?\*\*|__[^_\n]+?__|\*[^*\n]+?\*|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<>)"]+)/g;
  let lastIdx = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      nodes.push(<Fragment key={key++}>{text.slice(lastIdx, match.index)}</Fragment>);
    }
    const token = match[0];
    if (
      (token.startsWith('**') && token.endsWith('**')) ||
      (token.startsWith('__') && token.endsWith('__'))
    ) {
      nodes.push(
        <strong key={key++} className="font-bold text-[#131B2E] dark:text-white">
          {renderInline(token.slice(2, -2))}
        </strong>,
      );
    } else if (token.startsWith('*') && token.endsWith('*')) {
      nodes.push(
        <em key={key++} className="italic text-[#2B3752] dark:text-slate-200">
          {renderInline(token.slice(1, -1))}
        </em>,
      );
    } else if (token.startsWith('[')) {
      const linkMatch = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      if (linkMatch) {
        nodes.push(
          <a
            key={key++}
            href={linkMatch[2]}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-indigo-600 underline decoration-indigo-300 underline-offset-2 hover:text-indigo-700 dark:text-indigo-300 dark:decoration-indigo-500/60"
          >
            {linkMatch[1]}
          </a>,
        );
      } else {
        nodes.push(<Fragment key={key++}>{token}</Fragment>);
      }
    } else if (token.startsWith('http://') || token.startsWith('https://')) {
      let display = token.replace(/^https?:\/\/(www\.)?/, '');
      if (display.length > 42) display = `${display.slice(0, 39)}...`;
      nodes.push(
        <a
          key={key++}
          href={token}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-indigo-600 underline decoration-indigo-300 underline-offset-2 hover:text-indigo-700 dark:text-indigo-300 dark:decoration-indigo-500/60"
        >
          {display}
        </a>,
      );
    }
    lastIdx = tokenRegex.lastIndex;
  }

  if (lastIdx < text.length) {
    nodes.push(<Fragment key={key++}>{text.slice(lastIdx)}</Fragment>);
  }
  return nodes;
}

export function FormattedPostPreview({ content }: { content: string }) {
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i++;
      continue;
    }

    const headingMatch = trimmed.match(/^#{1,4}\s+(.+)$/);
    if (headingMatch) {
      const isSources = /^sources$/i.test(headingMatch[1].trim());
      blocks.push(
        <h4
          key={key++}
          className={
            isSources
              ? 'mt-3 border-t border-[#DCE2EC]/70 pt-3 text-[12px] font-bold uppercase tracking-wider text-[#5E6A82] dark:border-slate-700/70 dark:text-slate-400'
              : 'pt-2 text-[13px] font-bold tracking-tight text-[#131B2E] dark:text-white'
          }
        >
          {renderInline(headingMatch[1])}
        </h4>,
      );
      i++;
      continue;
    }

    if (/^[-*•]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*•]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*•]\s+/, ''));
        i++;
      }
      blocks.push(
        <ul key={key++} className="space-y-1.5 pl-4 text-[13px] leading-relaxed">
          {items.map((item, idx) => (
            <li key={idx} className="list-disc marker:text-indigo-500">
              {renderInline(item)}
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ''));
        i++;
      }
      blocks.push(
        <ol key={key++} className="space-y-1.5 pl-4 text-[13px] leading-relaxed">
          {items.map((item, idx) => (
            <li key={idx} className="list-decimal marker:font-semibold marker:text-indigo-500">
              {renderInline(item)}
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    blocks.push(
      <p key={key++} className="text-[13px] leading-relaxed text-[#131B2E] dark:text-slate-200">
        {renderInline(trimmed)}
      </p>,
    );
    i++;
  }

  return <div className="space-y-2.5">{blocks}</div>;
}
