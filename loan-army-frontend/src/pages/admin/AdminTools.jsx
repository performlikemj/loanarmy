import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
    Settings2, Plus, Copy, Trash2, Check, History, Pencil, X,
    AlertCircle, CheckCircle2, Loader2, Wifi, WifiOff, Database, Activity,
} from 'lucide-react'

const TEAM_OPTIONS = [
    { id: '33', name: 'Manchester United' },
    { id: '42', name: 'Arsenal' },
    { id: '49', name: 'Chelsea' },
    { id: '50', name: 'Manchester City' },
    { id: '40', name: 'Liverpool' },
    { id: '47', name: 'Tottenham' },
]

function ToggleField({ label, description, checked, onChange }) {
    return (
        <label className="flex items-start gap-3 p-3 rounded-lg border bg-muted/20 hover:bg-muted/40 transition-colors cursor-pointer">
            <input
                type="checkbox"
                checked={checked}
                onChange={(e) => onChange(e.target.checked)}
                className="h-4 w-4 mt-0.5 rounded border-gray-300"
            />
            <div>
                <div className="text-sm font-medium">{label}</div>
                {description && <div className="text-xs text-muted-foreground">{description}</div>}
            </div>
        </label>
    )
}

function NumberField({ label, description, value, onChange, min, max }) {
    return (
        <div className="space-y-1">
            <Label className="text-sm font-medium">{label}</Label>
            {description && <p className="text-xs text-muted-foreground">{description}</p>}
            <Input
                type="number"
                value={value}
                onChange={(e) => onChange(Number(e.target.value))}
                min={min}
                max={max}
                className="w-32"
            />
        </div>
    )
}

function ConfigEditor({ config, onSave, onCancel, saving }) {
    const [draft, setDraft] = useState(config)

    const updateField = (key, value) => setDraft(prev => ({ ...prev, [key]: value }))

    const toggleTeam = (teamId) => {
        setDraft(prev => {
            const teams = { ...prev.team_ids }
            if (teams[teamId]) {
                delete teams[teamId]
            } else {
                const opt = TEAM_OPTIONS.find(t => t.id === teamId)
                teams[teamId] = opt?.name || teamId
            }
            return { ...prev, team_ids: teams }
        })
    }

    const updateSeason = (index, value) => {
        setDraft(prev => {
            const seasons = [...prev.seasons]
            seasons[index] = Number(value)
            return { ...prev, seasons }
        })
    }

    const addSeason = () => {
        const max = Math.max(...draft.seasons, 2020)
        setDraft(prev => ({ ...prev, seasons: [...prev.seasons, max + 1] }))
    }

    const removeSeason = (index) => {
        setDraft(prev => ({
            ...prev,
            seasons: prev.seasons.filter((_, i) => i !== index),
        }))
    }

    const updateLeague = (index, field, value) => {
        setDraft(prev => {
            const leagues = prev.youth_leagues.map((l, i) =>
                i === index ? { ...l, [field]: field === 'fallback_id' ? Number(value) : value } : l
            )
            return { ...prev, youth_leagues: leagues }
        })
    }

    const addLeague = () => {
        setDraft(prev => ({
            ...prev,
            youth_leagues: [...prev.youth_leagues, { key: '', name: '', fallback_id: 0, level: 'U18' }],
        }))
    }

    const removeLeague = (index) => {
        setDraft(prev => ({
            ...prev,
            youth_leagues: prev.youth_leagues.filter((_, i) => i !== index),
        }))
    }

    return (
        <div className="space-y-6">
            {/* Team IDs */}
            <div className="space-y-2">
                <Label className="text-sm font-semibold">Teams</Label>
                <div className="flex flex-wrap gap-2">
                    {TEAM_OPTIONS.map(t => {
                        const selected = !!draft.team_ids?.[t.id]
                        return (
                            <button
                                key={t.id}
                                type="button"
                                onClick={() => toggleTeam(t.id)}
                                className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                                    selected
                                        ? 'bg-blue-600 text-white border-blue-600'
                                        : 'bg-white text-gray-700 border-gray-300 hover:border-gray-400'
                                }`}
                            >
                                {t.name} <span className="text-xs opacity-70">({t.id})</span>
                            </button>
                        )
                    })}
                </div>
            </div>

            {/* Seasons */}
            <div className="space-y-2">
                <Label className="text-sm font-semibold">Seasons</Label>
                <div className="flex flex-wrap items-center gap-2">
                    {draft.seasons.map((s, i) => (
                        <div key={i} className="flex items-center gap-1">
                            <Input
                                type="number"
                                value={s}
                                onChange={(e) => updateSeason(i, e.target.value)}
                                className="w-24"
                                min={2015}
                                max={2030}
                            />
                            <button
                                type="button"
                                onClick={() => removeSeason(i)}
                                className="p-1 text-gray-400 hover:text-red-500"
                            >
                                <X className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    ))}
                    <Button type="button" size="sm" variant="outline" onClick={addSeason}>
                        <Plus className="h-3.5 w-3.5 mr-1" /> Add
                    </Button>
                </div>
            </div>

            {/* Youth Leagues */}
            <div className="space-y-2">
                <Label className="text-sm font-semibold">Youth Leagues</Label>
                <div className="space-y-2">
                    {draft.youth_leagues.map((league, i) => (
                        <div key={i} className="flex items-center gap-2 p-2 rounded border bg-muted/20">
                            <Input
                                value={league.name}
                                onChange={(e) => updateLeague(i, 'name', e.target.value)}
                                placeholder="League name"
                                className="flex-1"
                            />
                            <Input
                                type="number"
                                value={league.fallback_id}
                                onChange={(e) => updateLeague(i, 'fallback_id', e.target.value)}
                                placeholder="API ID"
                                className="w-24"
                            />
                            <Input
                                value={league.level}
                                onChange={(e) => updateLeague(i, 'level', e.target.value)}
                                placeholder="Level"
                                className="w-20"
                            />
                            <button
                                type="button"
                                onClick={() => removeLeague(i)}
                                className="p-1 text-gray-400 hover:text-red-500"
                            >
                                <Trash2 className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    ))}
                    <Button type="button" size="sm" variant="outline" onClick={addLeague}>
                        <Plus className="h-3.5 w-3.5 mr-1" /> Add League
                    </Button>
                </div>
            </div>

            {/* Boolean toggles */}
            <div className="space-y-2">
                <Label className="text-sm font-semibold">Data Processing</Label>
                <div className="space-y-2">
                    <ToggleField
                        label="Use transfers for status"
                        description="Upgrade on_loan to sold/released using API-Football transfer data in Stage 6"
                        checked={draft.use_transfers_for_status}
                        onChange={(v) => updateField('use_transfers_for_status', v)}
                    />
                    <ToggleField
                        label="Assume full minutes if started"
                        description="Count starting XI as 90 minutes played regardless of actual data"
                        checked={draft.assume_full_minutes}
                        onChange={(v) => updateField('assume_full_minutes', v)}
                    />
                </div>
            </div>

            {/* Numeric settings */}
            <div className="space-y-2">
                <Label className="text-sm font-semibold">Thresholds</Label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <NumberField
                        label="Inactivity threshold (years)"
                        description="Seasons before marking as released"
                        value={draft.inactivity_threshold_years}
                        onChange={(v) => updateField('inactivity_threshold_years', v)}
                        min={1}
                        max={10}
                    />
                    <NumberField
                        label="Cohort timeout (sec)"
                        description="Max time for cohort discovery"
                        value={draft.cohort_discover_timeout}
                        onChange={(v) => updateField('cohort_discover_timeout', v)}
                        min={30}
                        max={600}
                    />
                    <NumberField
                        label="Player sync timeout (sec)"
                        description="Max time for player journey sync"
                        value={draft.player_sync_timeout}
                        onChange={(v) => updateField('player_sync_timeout', v)}
                        min={30}
                        max={300}
                    />
                </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-2 border-t">
                <Button onClick={() => onSave(draft)} disabled={saving}>
                    {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null}
                    Save Changes
                </Button>
                <Button variant="outline" onClick={onCancel} disabled={saving}>Cancel</Button>
            </div>
        </div>
    )
}

function HistoryTimeline({ history }) {
    if (!history?.length) {
        return <p className="text-sm text-muted-foreground">No changes recorded yet.</p>
    }
    return (
        <div className="space-y-3">
            {history.map((entry) => (
                <div key={entry.id} className="flex gap-3 text-sm">
                    <div className="w-2 h-2 mt-1.5 rounded-full bg-blue-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                        <div className="flex items-baseline gap-2 flex-wrap">
                            <span className="font-medium capitalize">{entry.action}</span>
                            <span className="text-xs text-muted-foreground">
                                {entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}
                            </span>
                        </div>
                        {entry.diff && Object.keys(entry.diff).length > 0 && (
                            <div className="mt-1 space-y-0.5">
                                {Object.entries(entry.diff).map(([key, { old: oldVal, new: newVal }]) => (
                                    <div key={key} className="text-xs text-muted-foreground font-mono">
                                        <span className="text-gray-600">{key}:</span>{' '}
                                        <span className="text-red-500 line-through">
                                            {typeof oldVal === 'object' ? JSON.stringify(oldVal) : String(oldVal)}
                                        </span>{' '}
                                        <span className="text-green-600">
                                            {typeof newVal === 'object' ? JSON.stringify(newVal) : String(newVal)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    )
}

function ApiFootballStatusCard() {
    const [status, setStatus] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    useEffect(() => {
        let cancelled = false
        ;(async () => {
            try {
                const data = await APIService.request('/api/admin/api-football/status', {}, { admin: true })
                if (!cancelled) setStatus(data)
            } catch (e) {
                if (!cancelled) setError(e.message)
            } finally {
                if (!cancelled) setLoading(false)
            }
        })()
        return () => { cancelled = true }
    }, [])

    const modeBadge = (mode) => {
        const variants = {
            direct: { className: 'bg-green-100 text-green-800', label: 'Direct' },
            rapidapi: { className: 'bg-blue-100 text-blue-800', label: 'RapidAPI' },
            stub: { className: 'bg-yellow-100 text-yellow-800', label: 'Stub' },
        }
        const v = variants[(mode || '').toLowerCase()] || { className: 'bg-gray-100 text-gray-800', label: mode || 'Unknown' }
        return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${v.className}`}>{v.label}</span>
    }

    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                    <Activity className="h-4 w-4" />
                    API-Football Connection
                </CardTitle>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" /> Checking status...
                    </div>
                ) : error ? (
                    <div className="flex items-center gap-2 text-sm text-red-600">
                        <WifiOff className="h-4 w-4" /> {error}
                    </div>
                ) : (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        <div>
                            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Mode</div>
                            <div className="flex items-center gap-2">
                                <Wifi className="h-3.5 w-3.5 text-green-600" />
                                {modeBadge(status.mode)}
                            </div>
                        </div>
                        <div>
                            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">API Key</div>
                            <div className="flex items-center gap-1.5 text-sm">
                                <div className={`h-2 w-2 rounded-full ${status.key_present ? 'bg-green-500' : 'bg-red-500'}`} />
                                {status.key_present
                                    ? <span className="font-mono text-xs">{status.key_prefix}****</span>
                                    : <span className="text-red-600">Missing</span>
                                }
                            </div>
                        </div>
                        <div>
                            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Today's Calls</div>
                            <div className="text-sm font-mono">
                                {status.usage?.total_today ?? '—'}
                            </div>
                        </div>
                        <div>
                            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Cache Entries</div>
                            <div className="flex items-center gap-1.5 text-sm">
                                <Database className="h-3.5 w-3.5 text-muted-foreground" />
                                <span className="font-mono">{status.cache?.total_entries ?? '—'}</span>
                            </div>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

export function AdminTools() {
    const { authToken } = useAuth()
    const adminReady = Boolean(authToken && APIService.isAdmin() && APIService.adminKey)

    const [configs, setConfigs] = useState([])
    const [selectedId, setSelectedId] = useState(null)
    const [selectedConfig, setSelectedConfig] = useState(null)
    const [editing, setEditing] = useState(false)
    const [creating, setCreating] = useState(false)
    const [newName, setNewName] = useState('')
    const [newNotes, setNewNotes] = useState('')
    const [cloneFrom, setCloneFrom] = useState(null)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [message, setMessage] = useState(null)
    const [showHistory, setShowHistory] = useState(false)

    const showMsg = (type, text) => {
        setMessage({ type, text })
        if (type === 'success') setTimeout(() => setMessage(null), 3000)
    }

    const loadConfigs = useCallback(async () => {
        try {
            const data = await APIService.request('/api/admin/rebuild-configs', {}, { admin: true })
            setConfigs(data || [])
        } catch (e) {
            showMsg('error', `Failed to load configs: ${e.message}`)
        } finally {
            setLoading(false)
        }
    }, [])

    const loadConfig = useCallback(async (id) => {
        try {
            const data = await APIService.request(`/api/admin/rebuild-configs/${id}`, {}, { admin: true })
            setSelectedConfig(data)
            setSelectedId(id)
            setShowHistory(false)
        } catch (e) {
            showMsg('error', `Failed to load config: ${e.message}`)
        }
    }, [])

    useEffect(() => {
        if (adminReady) loadConfigs()
    }, [adminReady, loadConfigs])

    // Auto-select active config
    useEffect(() => {
        if (configs.length && !selectedId) {
            const active = configs.find(c => c.is_active)
            if (active) loadConfig(active.id)
        }
    }, [configs, selectedId, loadConfig])

    const handleCreate = async () => {
        if (!newName.trim()) return showMsg('error', 'Name is required')
        setSaving(true)
        try {
            const body = { name: newName.trim(), notes: newNotes }
            if (cloneFrom) body.clone_from = cloneFrom
            await APIService.request('/api/admin/rebuild-configs', {
                method: 'POST',
                body: JSON.stringify(body),
            }, { admin: true })
            showMsg('success', `Config "${newName}" created`)
            setCreating(false)
            setNewName('')
            setNewNotes('')
            setCloneFrom(null)
            await loadConfigs()
        } catch (e) {
            showMsg('error', e.message)
        } finally {
            setSaving(false)
        }
    }

    const handleSave = async (configData) => {
        setSaving(true)
        try {
            const body = { config: configData }
            await APIService.request(`/api/admin/rebuild-configs/${selectedId}`, {
                method: 'PUT',
                body: JSON.stringify(body),
            }, { admin: true })
            showMsg('success', 'Config saved')
            setEditing(false)
            await loadConfig(selectedId)
            await loadConfigs()
        } catch (e) {
            showMsg('error', e.message)
        } finally {
            setSaving(false)
        }
    }

    const handleActivate = async (id) => {
        try {
            await APIService.request(`/api/admin/rebuild-configs/${id}/activate`, {
                method: 'POST',
            }, { admin: true })
            showMsg('success', 'Config activated')
            await loadConfigs()
            await loadConfig(id)
        } catch (e) {
            showMsg('error', e.message)
        }
    }

    const handleDelete = async (id) => {
        const name = configs.find(c => c.id === id)?.name
        if (!confirm(`Delete config "${name}"?`)) return
        try {
            await APIService.request(`/api/admin/rebuild-configs/${id}`, {
                method: 'DELETE',
            }, { admin: true })
            showMsg('success', `Config "${name}" deleted`)
            if (selectedId === id) {
                setSelectedId(null)
                setSelectedConfig(null)
            }
            await loadConfigs()
        } catch (e) {
            showMsg('error', e.message)
        }
    }

    const handleUpdateNotes = async (notes) => {
        try {
            await APIService.request(`/api/admin/rebuild-configs/${selectedId}`, {
                method: 'PUT',
                body: JSON.stringify({ notes }),
            }, { admin: true })
            setSelectedConfig(prev => ({ ...prev, notes }))
        } catch (e) {
            showMsg('error', e.message)
        }
    }

    if (!adminReady) {
        return (
            <div className="space-y-6">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Tools</h2>
                    <p className="text-muted-foreground mt-1">Sign in as admin to manage tools and configurations</p>
                </div>
                <Card>
                    <CardContent className="pt-6">
                        <div className="rounded-lg border border-dashed bg-muted/40 p-6 text-sm text-muted-foreground">
                            <p>Admin access required. Go to Settings to configure authentication.</p>
                        </div>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Tools</h2>
                <p className="text-muted-foreground mt-1">API connection status and rebuild configurations</p>
            </div>

            <ApiFootballStatusCard />

            <div className="flex items-center justify-between">
                <h3 className="text-xl font-semibold tracking-tight">Rebuild Configs</h3>
                <Button onClick={() => { setCreating(true); setCloneFrom(null) }}>
                    <Plus className="h-4 w-4 mr-1" /> New Config
                </Button>
            </div>

            {message && (
                <Alert className={message.type === 'error' ? 'border-red-500 bg-red-50' : 'border-green-500 bg-green-50'}>
                    {message.type === 'error'
                        ? <AlertCircle className="h-4 w-4 text-red-600" />
                        : <CheckCircle2 className="h-4 w-4 text-green-600" />}
                    <AlertDescription className={message.type === 'error' ? 'text-red-800' : 'text-green-800'}>
                        {message.text}
                    </AlertDescription>
                </Alert>
            )}

            {/* Create dialog */}
            {creating && (
                <Card>
                    <CardHeader>
                        <CardTitle>New Configuration</CardTitle>
                        <CardDescription>
                            {cloneFrom ? `Cloning from existing config` : 'Create from default values'}
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="space-y-1">
                            <Label>Name</Label>
                            <Input
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                                placeholder="e.g. Big 6 with transfers"
                            />
                        </div>
                        <div className="space-y-1">
                            <Label>Notes (optional)</Label>
                            <Input
                                value={newNotes}
                                onChange={(e) => setNewNotes(e.target.value)}
                                placeholder="Description of this configuration"
                            />
                        </div>
                        <div className="flex gap-2">
                            <Button onClick={handleCreate} disabled={saving}>
                                {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null}
                                Create
                            </Button>
                            <Button variant="outline" onClick={() => setCreating(false)}>Cancel</Button>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Config list */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Settings2 className="h-5 w-5" />
                        Saved Configurations
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin" /> Loading...
                        </div>
                    ) : configs.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No configurations yet.</p>
                    ) : (
                        <div className="space-y-2">
                            {configs.map(c => (
                                <div
                                    key={c.id}
                                    className={`flex items-center gap-3 p-3 rounded-lg border transition-colors cursor-pointer ${
                                        selectedId === c.id ? 'border-blue-500 bg-blue-50' : 'hover:bg-muted/40'
                                    }`}
                                    onClick={() => loadConfig(c.id)}
                                >
                                    <div className={`h-2.5 w-2.5 rounded-full shrink-0 ${c.is_active ? 'bg-green-500' : 'bg-gray-300'}`} />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="font-medium text-sm">{c.name}</span>
                                            {c.is_active && (
                                                <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-green-100 text-green-700">
                                                    Active
                                                </span>
                                            )}
                                        </div>
                                        <span className="text-xs text-muted-foreground">
                                            Updated {c.updated_at ? new Date(c.updated_at).toLocaleDateString() : 'never'}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-1 shrink-0">
                                        {!c.is_active && (
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={(e) => { e.stopPropagation(); handleActivate(c.id) }}
                                                title="Activate"
                                            >
                                                <Check className="h-3.5 w-3.5" />
                                            </Button>
                                        )}
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            onClick={(e) => {
                                                e.stopPropagation()
                                                setCloneFrom(c.id)
                                                setNewName(`${c.name} (copy)`)
                                                setCreating(true)
                                            }}
                                            title="Clone"
                                        >
                                            <Copy className="h-3.5 w-3.5" />
                                        </Button>
                                        {!c.is_active && (
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={(e) => { e.stopPropagation(); handleDelete(c.id) }}
                                                title="Delete"
                                                className="text-red-500 hover:text-red-700"
                                            >
                                                <Trash2 className="h-3.5 w-3.5" />
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Selected config detail */}
            {selectedConfig && !editing && (
                <Card>
                    <CardHeader>
                        <div className="flex items-start justify-between gap-3">
                            <div>
                                <CardTitle>{selectedConfig.name}</CardTitle>
                                <CardDescription>
                                    {selectedConfig.notes || 'No notes'}
                                    <button
                                        className="ml-2 text-blue-600 hover:underline text-xs"
                                        onClick={() => {
                                            const notes = prompt('Edit notes:', selectedConfig.notes || '')
                                            if (notes !== null) handleUpdateNotes(notes)
                                        }}
                                    >
                                        edit
                                    </button>
                                </CardDescription>
                            </div>
                            <div className="flex gap-2 shrink-0">
                                <Button
                                    size="sm"
                                    variant={showHistory ? 'secondary' : 'outline'}
                                    onClick={() => setShowHistory(!showHistory)}
                                >
                                    <History className="h-3.5 w-3.5 mr-1" />
                                    History
                                </Button>
                                <Button size="sm" onClick={() => setEditing(true)}>
                                    <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
                                </Button>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        {showHistory ? (
                            <HistoryTimeline history={selectedConfig.history} />
                        ) : (
                            <div className="space-y-4">
                                {/* Summary view */}
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Teams</div>
                                        <div className="flex flex-wrap gap-1">
                                            {Object.entries(selectedConfig.config?.team_ids || {}).map(([id, name]) => (
                                                <span key={id} className="px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-800">
                                                    {name}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                    <div>
                                        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Seasons</div>
                                        <div className="flex flex-wrap gap-1">
                                            {(selectedConfig.config?.seasons || []).map(s => (
                                                <span key={s} className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-800">
                                                    {s}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                </div>

                                <div>
                                    <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Youth Leagues</div>
                                    <div className="space-y-1">
                                        {(selectedConfig.config?.youth_leagues || []).map((l, i) => (
                                            <div key={i} className="text-sm flex items-center gap-2">
                                                <span className="font-mono text-xs text-muted-foreground w-12">{l.fallback_id}</span>
                                                <span>{l.name}</span>
                                                <span className="text-xs text-muted-foreground">({l.level})</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2 border-t">
                                    {[
                                        ['Transfers for status', selectedConfig.config?.use_transfers_for_status],
                                        ['Full minutes assumed', selectedConfig.config?.assume_full_minutes],
                                    ].map(([label, val]) => (
                                        <div key={label} className="flex items-center gap-2 text-sm">
                                            <div className={`h-2 w-2 rounded-full ${val ? 'bg-green-500' : 'bg-gray-300'}`} />
                                            {label}
                                        </div>
                                    ))}
                                    {[
                                        ['Inactivity', `${selectedConfig.config?.inactivity_threshold_years}y`],
                                        ['Cohort timeout', `${selectedConfig.config?.cohort_discover_timeout}s`],
                                        ['Player timeout', `${selectedConfig.config?.player_sync_timeout}s`],
                                    ].map(([label, val]) => (
                                        <div key={label} className="text-sm">
                                            <span className="text-muted-foreground">{label}: </span>
                                            <span className="font-mono">{val}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Editor */}
            {selectedConfig && editing && (
                <Card>
                    <CardHeader>
                        <CardTitle>Editing: {selectedConfig.name}</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ConfigEditor
                            config={selectedConfig.config}
                            onSave={handleSave}
                            onCancel={() => setEditing(false)}
                            saving={saving}
                        />
                    </CardContent>
                </Card>
            )}
        </div>
    )
}
