/**
 * MarkdownMessage — renders chat messages as rich markdown.
 * Supports code blocks with syntax highlighting, tables, links, etc.
 */

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

const components: Components = {
  // Code blocks with dark theme
  code({ className, children, ...props }) {
    const isInline = !className
    if (isInline) {
      return (
        <code className="rounded-md bg-emerald-950/50 px-1.5 py-0.5 text-[11px] text-emerald-300" {...props}>
          {children}
        </code>
      )
    }
    const lang = className?.replace('language-', '') || ''
    return (
      <div className="group relative my-2 overflow-hidden rounded-xl border border-white/5 bg-[#0a0a0c]">
        {lang && (
          <div className="border-b border-white/5 px-4 py-1.5 text-[9px] font-mono tracking-[0.2em] text-zinc-600 uppercase">
            {lang}
          </div>
        )}
        <pre className="scrollbar-small overflow-x-auto p-4 text-[12px] leading-6">
          <code className={`font-mono text-emerald-200 ${className}`} {...props}>
            {children}
          </code>
        </pre>
      </div>
    )
  },
  // Links
  a({ href, children }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-emerald-400 underline underline-offset-2 hover:text-emerald-300">
        {children}
      </a>
    )
  },
  // Lists
  ul({ children }) {
    return <ul className="ml-4 list-disc space-y-1 text-zinc-300 marker:text-emerald-600">{children}</ul>
  },
  ol({ children }) {
    return <ol className="ml-4 list-decimal space-y-1 text-zinc-300 marker:text-emerald-600">{children}</ol>
  },
  li({ children }) {
    return <li className="text-xs leading-6">{children}</li>
  },
  // Bold / Italic
  strong({ children }) {
    return <strong className="font-bold text-white">{children}</strong>
  },
  em({ children }) {
    return <em className="text-zinc-200 italic">{children}</em>
  },
  // Headings
  h1({ children }) {
    return <h1 className="mt-3 mb-2 text-sm font-black text-white tracking-wide">{children}</h1>
  },
  h2({ children }) {
    return <h2 className="mt-2 mb-1 text-xs font-bold text-white tracking-wide">{children}</h2>
  },
  h3({ children }) {
    return <h3 className="mt-2 mb-1 text-xs font-bold text-zinc-200">{children}</h3>
  },
  // Blockquote
  blockquote({ children }) {
    return (
      <blockquote className="my-2 border-l-2 border-emerald-500/40 pl-3 text-zinc-400 italic">
        {children}
      </blockquote>
    )
  },
  // Tables
  table({ children }) {
    return (
      <div className="my-2 overflow-x-auto rounded-xl border border-white/5">
        <table className="w-full text-[11px]">{children}</table>
      </div>
    )
  },
  thead({ children }) {
    return <thead className="border-b border-white/10 bg-white/[0.03]">{children}</thead>
  },
  th({ children }) {
    return <th className="px-3 py-2 text-left font-bold text-zinc-300 tracking-wider uppercase text-[10px]">{children}</th>
  },
  td({ children }) {
    return <td className="border-t border-white/5 px-3 py-2 text-zinc-400">{children}</td>
  },
  // Horizontal rule
  hr() {
    return <hr className="my-3 border-white/10" />
  },
  // Paragraphs
  p({ children }) {
    return <p className="my-1 text-xs leading-6">{children}</p>
  },
}

interface MarkdownMessageProps {
  content: string
  className?: string
}

export default function MarkdownMessage({ content, className = '' }: MarkdownMessageProps) {
  return (
    <div className={`prose-jarvis ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
