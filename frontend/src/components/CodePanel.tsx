// frontend/src/components/CodePanel.tsx
import Editor from '@monaco-editor/react'
import { cn } from '@/lib/utils'

interface CodePanelProps {
  language: string
  value: string
  readOnly?: boolean
  onChange?: (v: string) => void
  onReset?: () => void       // editable mode: reset to original content
  onDownload?: () => void    // readOnly mode: download file
  height?: string
}

export function CodePanel({
  language, value, readOnly = false,
  onChange, onReset, onDownload, height = '400px',
}: CodePanelProps) {
  return (
    <div className={cn("relative border rounded-md overflow-hidden")}>
      {/* Action buttons */}
      <div className="absolute top-2 right-2 z-10 flex gap-2">
        {!readOnly && onReset && (
          <button
            type="button"
            onClick={onReset}
            className="px-2 py-1 text-xs bg-white border rounded shadow-sm hover:bg-gray-50"
          >
            Reset
          </button>
        )}
        {readOnly && onDownload && (
          <button
            type="button"
            onClick={onDownload}
            className="px-2 py-1 text-xs bg-white border rounded shadow-sm hover:bg-gray-50"
          >
            Download
          </button>
        )}
      </div>

      {/* Monaco Editor — @monaco-editor/react has built-in lazy loading */}
      <Editor
        height={height}
        language={language}
        value={value}
        options={{
          readOnly,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          fontSize: 13,
          lineNumbers: 'on',
        }}
        onChange={(v) => !readOnly && onChange?.(v ?? '')}
      />
    </div>
  )
}
