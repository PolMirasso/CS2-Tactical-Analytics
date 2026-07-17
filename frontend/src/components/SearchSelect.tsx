import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

export interface SearchOption {
  id: string
  name: string
}

interface Props {
  options: SearchOption[]
  value: string
  onChange: (id: string) => void
  allLabel?: string
  placeholder?: string
  id?: string
  disabled?: boolean
  className?: string
}

export function SearchSelect({
  options,
  value,
  onChange,
  allLabel,
  placeholder,
  id,
  disabled,
  className,
}: Props) {
  const { t } = useTranslation()
  const all = useMemo<SearchOption[]>(
    () => (allLabel != null ? [{ id: '', name: allLabel }, ...options] : options),
    [options, allLabel],
  )
  const selectedName = all.find((o) => o.id === value)?.name ?? ''

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState(selectedName)
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) setQuery(selectedName)
  }, [selectedName, open])

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
    if (!open || q === '' || q === selectedName.toLowerCase()) return all
    return all.filter((o) => o.name.toLowerCase().includes(q))
  }, [all, query, open, selectedName])

  const commit = (o: SearchOption) => {
    onChange(o.id)
    setQuery(o.name)
    setOpen(false)
  }

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
        commit(filtered[active])
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={rootRef} className={`relative ${className ?? 'mb-3'}`}>
      <input
        id={id}
        type="text"
        role="combobox"
        aria-expanded={open}
        autoComplete="off"
        disabled={disabled}
        value={open ? query : selectedName}
        placeholder={placeholder ?? t('common.searchTeam')}
        onFocus={() => { if (!disabled) { setOpen(true); setQuery(''); setActive(0) } }}
        onClick={() => { if (!disabled) setOpen(true) }}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0) }}
        onKeyDown={onKeyDown}
        className="!mb-0 w-full"
      />
      {open && (
        <ul
          role="listbox"
          className="absolute inset-x-0 top-full z-20 mt-1 max-h-64 overflow-y-auto rounded-md border border-border bg-surface-2 py-1 shadow-lg"
        >
          {filtered.length === 0 ? (
            <li className="px-2.5 py-1.5 text-sm text-muted">{t('common.noResults')}</li>
          ) : (
            filtered.map((o, i) => (
              <li
                key={o.id || '__all__'}
                role="option"
                aria-selected={o.id === value}
                onMouseDown={(e) => { e.preventDefault(); commit(o) }}
                onMouseEnter={() => setActive(i)}
                className={`cursor-pointer px-2.5 py-1.5 text-sm ${
                  i === active
                    ? 'bg-accent text-accent-text'
                    : o.id === value
                      ? 'text-accent'
                      : 'text-text'
                }`}
              >
                {o.name}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}
