import { useTranslation } from 'react-i18next'
import { ZoneScatter } from './ZoneScatter'
import { useMaps } from './hooks'

const RESERVE_MAPS = ['de_train', 'de_vertigo']

export function MapsPage() {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useMaps()

  const active = data?.filter((m) => !RESERVE_MAPS.includes(m.id)) ?? []
  const reserve = data?.filter((m) => RESERVE_MAPS.includes(m.id)) ?? []

  const renderMap = (map: NonNullable<typeof data>[number]) => (
    <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid" key={map.id}>
      <h2>
        {map.name}{' '}
        <span className="text-muted">
          ({map.zones.length} {t('maps.zones')})
        </span>
      </h2>
      <div className="flex flex-wrap gap-6">
        <ZoneScatter zones={map.zones} mapId={map.id} />
        <table className="min-w-[240px] flex-1">
          <thead>
            <tr>
              <th>{t('maps.title')}</th>
              <th>{t('maps.region')}</th>
            </tr>
          </thead>
          <tbody>
            {map.zones.map((z) => (
              <tr key={z.id}>
                <td>{z.name}</td>
                <td>
                  <span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">{z.region}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )

  return (
    <div>
      <h1>{t('maps.title')}</h1>
      {isLoading && <p className="text-muted">{t('common.loading')}</p>}
      {isError && <p className="my-2 text-[0.9rem] text-danger">{t('common.error')}</p>}
      {active.length > 0 && (
        <>
          <h2>{t('maps.activeDuty')}</h2>
          {active.map(renderMap)}
        </>
      )}
      {reserve.length > 0 && (
        <>
          <h2>{t('maps.reserve')}</h2>
          {reserve.map(renderMap)}
        </>
      )}
    </div>
  )
}
