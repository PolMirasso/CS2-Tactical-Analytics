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
      <label htmlFor="team-search">{t('common.search')}</label>
      <input
        id="team-search"
        value={term}
        placeholder={t('hltv.searchPlaceholder')}
        onChange={(e) => setTerm(e.target.value)}
      />
      {isFetching && <p className="text-muted">{t('common.loading')}</p>}
      {data && data.length > 0 && (
        <table>
          <tbody>
            {data.map((team) => (
              <tr key={team.id}>
                <td>{team.name}</td>
                <td className="text-muted">#{team.id}</td>
                <td className="text-right">
                  <button className="border border-border bg-transparent text-text" onClick={() => onSelect(team)}>
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
