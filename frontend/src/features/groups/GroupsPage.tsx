import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate } from '@/lib/format'
import {
  useCreateGroup,
  useGroups,
  useInvitations,
  useInviteMember,
  useRespondInvitation,
} from './hooks'

export function GroupsPage() {
  const { t } = useTranslation()
  const { data: groups } = useGroups()
  const { data: invitations } = useInvitations()
  const createGroup = useCreateGroup()
  const invite = useInviteMember()
  const respond = useRespondInvitation()

  const [name, setName] = useState('')
  const [inviteEmail, setInviteEmail] = useState<Record<number, string>>({})

  return (
    <div>
      <h1>{t('groups.title')}</h1>

      <div className="card">
        <h2>{t('groups.create')}</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (!name.trim()) return
            createGroup.mutate(name, { onSuccess: () => setName('') })
          }}
        >
          <div className="row" style={{ maxWidth: 480 }}>
            <input
              placeholder={t('groups.name')}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button type="submit" disabled={createGroup.isPending}>
              {t('groups.create')}
            </button>
          </div>
        </form>
      </div>

      <div className="card">
        <h2>{t('groups.title')}</h2>
        {!groups || groups.length === 0 ? (
          <p className="muted">{t('groups.noGroups')}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t('groups.name')}</th>
                <th>{t('groups.members')}</th>
                <th>{t('groups.invite')}</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g.id}>
                  <td>
                    {g.name}{' '}
                    {g.is_owner && <span className="badge">{t('groups.owner')}</span>}
                  </td>
                  <td>{g.member_count}</td>
                  <td>
                    <div className="row" style={{ minWidth: 260 }}>
                      <input
                        placeholder={t('groups.inviteEmail')}
                        value={inviteEmail[g.id] ?? ''}
                        onChange={(e) =>
                          setInviteEmail((m) => ({ ...m, [g.id]: e.target.value }))
                        }
                      />
                      <button
                        className="ghost"
                        disabled={invite.isPending || !inviteEmail[g.id]}
                        onClick={() =>
                          invite.mutate(
                            { groupId: g.id, email: inviteEmail[g.id] },
                            {
                              onSuccess: () =>
                                setInviteEmail((m) => ({ ...m, [g.id]: '' })),
                            },
                          )
                        }
                      >
                        {t('groups.invite')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>{t('groups.invitations')}</h2>
        {!invitations || invitations.length === 0 ? (
          <p className="muted">{t('groups.noInvitations')}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t('groups.name')}</th>
                <th>{t('groups.from')}</th>
                <th>{t('demos.status')}</th>
                <th>{t('demos.created')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {invitations.map((inv) => (
                <tr key={inv.id}>
                  <td>{inv.group_name}</td>
                  <td className="muted">{inv.inviter_email}</td>
                  <td>
                    <span className="badge">{inv.status}</span>
                  </td>
                  <td className="muted">{formatDate(inv.created_at)}</td>
                  <td>
                    {inv.status === 'pending' && (
                      <div className="row" style={{ minWidth: 200 }}>
                        <button
                          onClick={() => respond.mutate({ id: inv.id, accept: true })}
                          disabled={respond.isPending}
                        >
                          {t('groups.accept')}
                        </button>
                        <button
                          className="ghost"
                          onClick={() => respond.mutate({ id: inv.id, accept: false })}
                          disabled={respond.isPending}
                        >
                          {t('groups.decline')}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
