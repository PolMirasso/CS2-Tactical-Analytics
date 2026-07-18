import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

export interface SearchOption {
  id: string
  name: string
}

interface Props {
  options: SearchOption[]
  values: string[]
  onChange: (ids: string[]) => void
  placeholder?: string
  id?: string
  disabled?: boolean
  className?: string
}

export function MultiSelect({
  options,
  values,
  onChange,
  placeholder,
  id,
  disabled,
  className,
}: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const byId = useMemo(() => new Map(options.map((o) => [o.id, o])), [options])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q === '') return options
    return options.filter((o) => o.name.toLowerCase().includes(q))
  }, [options, query])

  const toggle = (optId: string) => {
    onChange(values.includes(optId) ? values.filter((v) => v !== optId) : [...values, optId])
    setQuery('')
    inputRef.current?.focus()
  }
  const remove = (optId: string) => onChange(values.filter((v) => v !== optId))

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setActive((a) => Math.min(a + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter') {
      if (open && filtered[active]) {
        e.preventDefault()
        toggle(filtered[active].id)
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    } else if (e.key === 'Backspace' && query === '' && values.length > 0) {
      remove(values[values.length - 1])
    }
  }

  return (
    <div ref={rootRef} className={`relative ${className ?? 'mb-3'}`}>
      <div
        className={`flex min-h-[42px] flex-wrap items-center gap-1 rounded-md border border-border bg-surface-2 px-1.5 py-1 focus-within:border-accent ${
          disabled ? 'opacity-50' : 'cursor-text'
        }`}
        onClick={() => { if (!disabled) { setOpen(true); inputRef.current?.focus() } }}
      >
        {values.map((v) => (
          <span
            key={v}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2 py-0.5 text-xs"
          >
            {byId.get(v)?.name ?? v}
            <button
              type="button"
              className="border-none bg-transparent p-0 leading-none text-muted"
              onClick={(e) => { e.stopPropagation(); remove(v) }}
              aria-label={t('common.remove')}
            >
              ✕
            </button>
          </span>
        ))}
        <input
          id={id}
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={open}
          autoComplete="off"
          disabled={disabled}
          value={query}
          placeholder={values.length === 0 ? (placeholder ?? t('common.searchTeam')) : ''}
          onFocus={() => { if (!disabled) { setOpen(true); setActive(0) } }}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0) }}
          onKeyDown={onKeyDown}
          className="!mb-0 w-auto min-w-[80px] flex-1 border-none bg-transparent px-1 py-0.5 outline-none"
        />
      </div>
      {open && (
        <ul
          role="listbox"
          aria-multiselectable="true"
          className="absolute inset-x-0 top-full z-20 mt-1 max-h-64 overflow-y-auto rounded-md border border-border bg-surface-2 py-1 shadow-lg"
        >
          {filtered.length === 0 ? (
            <li className="px-2.5 py-1.5 text-sm text-muted">{t('common.noResults')}</li>
          ) : (
            filtered.map((o, i) => {
              const on = values.includes(o.id)
              return (
                <li
                  key={o.id}
                  role="option"
                  aria-selected={on}
                  onMouseDown={(e) => { e.preventDefault(); toggle(o.id) }}
                  onMouseEnter={() => setActive(i)}
                  className={`flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-sm ${
                    i === active ? 'bg-accent text-accent-text' : on ? 'text-accent' : 'text-text'
                  }`}
                >
                  <span className="inline-block w-3">{on ? '✓' : ''}</span>
                  {o.name}
                </li>
              )
            })
          )}
        </ul>
      )}
    </div>
  )
}
