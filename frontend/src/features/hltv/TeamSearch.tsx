import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import type { TeamHit } from '@/types/api'
import { hltvApi } from './api'

interface Props {
  onSelect: (team: TeamHit) => void
}

export function TeamSearch({ onSelect }: Props) {
  const { t } = useTranslation()
  const [term, setTerm] = useState('')

  const { data, isFetching } = useQuery({
    queryKey: ['hltv', 'search', term],
    queryFn: () => hltvApi.searchTeams(term),
    enabled: term.trim().length >= 2,
  })

  return (
    <div>
      <label className="mb-1 block text-[0.85rem] text-muted" htmlFor="team-search">{t('common.search')}</label>
      <input
        id="team-search"
        className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
        value={term}
        placeholder={t('hltv.searchPlaceholder')}
        onChange={(e) => setTerm(e.target.value)}
      />
      {isFetching && <p className="my-4 text-muted">{t('common.loading')}</p>}
      {data && data.length > 0 && (
        <table className="w-full border-collapse text-[0.9rem]">
          <tbody>
            {data.map((team) => (
              <tr key={team.id}>
                <td className="border-b border-border px-2.5 py-2 text-left">{team.name}</td>
                <td className="border-b border-border px-2.5 py-2 text-left text-muted">#{team.id}</td>
                <td className="border-b border-border px-2.5 py-2 text-right">
                  <button className="cursor-pointer rounded-md border border-border bg-transparent px-3.5 py-2 font-[inherit] text-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onSelect(team)}>
                    {t('hltv.selectTeam')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
