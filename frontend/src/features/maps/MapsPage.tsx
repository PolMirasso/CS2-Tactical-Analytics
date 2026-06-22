import { useTranslation } from 'react-i18next'
import { ZoneScatter } from './ZoneScatter'
import { useMaps } from './hooks'

export function MapsPage() {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useMaps()

  return (
    <div>
      <h1>{t('maps.title')}</h1>
      {isLoading && <p className="muted">{t('common.loading')}</p>}
      {isError && <p className="error">{t('common.error')}</p>}
      {data?.map((map) => (
        <div className="card" key={map.id}>
          <h2>
            {map.name}{' '}
            <span className="muted">
              ({map.zones.length} {t('maps.zones')})
            </span>
          </h2>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <ZoneScatter zones={map.zones} mapId={map.id} />
            <table style={{ flex: 1, minWidth: 240 }}>
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
                      <span className="badge">{z.region}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}
