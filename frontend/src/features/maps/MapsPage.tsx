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
      <h2 className="mb-3 text-[1.1rem]">
        {map.name}{' '}
        <span className="text-muted">
          ({map.zones.length} {t('maps.zones')})
        </span>
      </h2>
      <div className="flex flex-wrap gap-6">
        <ZoneScatter zones={map.zones} mapId={map.id} />
        <table className="w-full border-collapse text-[0.9rem] min-w-[240px] flex-1">
          <thead>
            <tr>
              <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('maps.title')}</th>
              <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('maps.region')}</th>
            </tr>
          </thead>
          <tbody>
            {map.zones.map((z) => (
              <tr key={z.id}>
                <td className="border-b border-border px-2.5 py-2 text-left">{z.name}</td>
                <td className="border-b border-border px-2.5 py-2 text-left">
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
      <h1 className="mb-4 text-[1.4rem]">{t('maps.title')}</h1>
      {isLoading && <p className="my-4 text-muted">{t('common.loading')}</p>}
      {isError && <p className="my-2 text-[0.9rem] text-danger">{t('common.error')}</p>}
      {active.length > 0 && (
        <>
          <h2 className="mb-3 text-[1.1rem]">{t('maps.activeDuty')}</h2>
          {active.map(renderMap)}
        </>
      )}
      {reserve.length > 0 && (
        <>
          <h2 className="mb-3 text-[1.1rem]">{t('maps.reserve')}</h2>
          {reserve.map(renderMap)}
        </>
      )}
    </div>
  )
}
