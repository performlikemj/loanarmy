import { useState, useEffect, useCallback, useRef } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
    Search, Loader2, AlertCircle, CheckCircle2, ArrowRight,
    ChevronDown, ChevronRight, User,
} from 'lucide-react'

const STATUS_COLORS = {
    academy: 'bg-blue-100 text-blue-800',
    first_team: 'bg-green-100 text-green-800',
    on_loan: 'bg-yellow-100 text-yellow-800',
    released: 'bg-red-100 text-red-800',
    sold: 'bg-purple-100 text-purple-800',
}

const RESULT_COLORS = {
    match: 'bg-green-100 text-green-700 border-green-300',
    pass: 'bg-gray-100 text-gray-600 border-gray-300',
}

function StatusBadge({ status }) {
    return (
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[status] || 'bg-gray-100 text-gray-700'}`}>
            {status}
        </span>
    )
}

export function AdminSandbox() {
    // Search state
    const [searchQuery, setSearchQuery] = useState('')
    const [searchResults, setSearchResults] = useState([])
    const [searching, setSearching] = useState(false)
    const [showResults, setShowResults] = useState(false)
    const searchRef = useRef(null)
    const debounceRef = useRef(null)

    // Tracked player picker
    const [trackedPlayers, setTrackedPlayers] = useState([])
    const [trackedTeamFilter, setTrackedTeamFilter] = useState('')

    // Selected player
    const [selectedPlayer, setSelectedPlayer] = useState(null)
    const [parentOverride, setParentOverride] = useState('')
    const [forceSync, setForceSync] = useState(false)

    // Results
    const [classifying, setClassifying] = useState(false)
    const [result, setResult] = useState(null)
    const [error, setError] = useState(null)
    const [expandedClassification, setExpandedClassification] = useState(null)

    // Load tracked players for picker
    useEffect(() => {
        APIService.request('/admin/tracked-players?per_page=500', {}, { admin: true })
            .then((data) => setTrackedPlayers(data?.items || []))
            .catch(() => {})
    }, [])

    // Debounced API search
    const handleSearch = useCallback((query) => {
        setSearchQuery(query)
        if (debounceRef.current) clearTimeout(debounceRef.current)
        if (!query || query.length < 2) {
            setSearchResults([])
            setShowResults(false)
            return
        }
        debounceRef.current = setTimeout(async () => {
            setSearching(true)
            try {
                const data = await APIService.request(
                    `/admin/players/search-api?q=${encodeURIComponent(query)}`,
                    {},
                    { admin: true }
                )
                setSearchResults(data?.results || [])
                setShowResults(true)
            } catch {
                setSearchResults([])
            } finally {
                setSearching(false)
            }
        }, 400)
    }, [])

    const selectPlayer = (player) => {
        setSelectedPlayer(player)
        setShowResults(false)
        setSearchQuery(player.name || '')
        setResult(null)
        setError(null)
    }

    const selectTrackedPlayer = (tp) => {
        setSelectedPlayer({
            id: tp.player_api_id,
            name: tp.player_name,
            photo: tp.photo_url,
            team: tp.loan_club_name || (tp.team?.name),
        })
        setSearchQuery(tp.player_name || '')
        setResult(null)
        setError(null)
    }

    const runClassification = async () => {
        if (!selectedPlayer?.id) return
        setClassifying(true)
        setError(null)
        setResult(null)
        try {
            const body = {
                player_api_id: selectedPlayer.id,
                force_sync: forceSync,
            }
            if (parentOverride) body.parent_api_id = parseInt(parentOverride)
            const data = await APIService.request('/admin/players/test-classify', {
                method: 'POST',
                body: JSON.stringify(body),
            }, { admin: true })
            setResult(data)
            if (data.classifications?.length > 0) {
                setExpandedClassification(0)
            }
        } catch (e) {
            setError(e.message || 'Classification failed')
        } finally {
            setClassifying(false)
        }
    }

    // Close search dropdown on outside click
    useEffect(() => {
        const handler = (e) => {
            if (searchRef.current && !searchRef.current.contains(e.target)) {
                setShowResults(false)
            }
        }
        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [])

    // Unique teams from tracked players
    const trackedTeams = [...new Map(
        trackedPlayers
            .filter((tp) => tp.team?.name)
            .map((tp) => [tp.team?.id, tp.team])
    ).values()].sort((a, b) => (a.name || '').localeCompare(b.name || ''))

    const filteredTracked = trackedTeamFilter
        ? trackedPlayers.filter((tp) => tp.team?.id === parseInt(trackedTeamFilter))
        : trackedPlayers

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Player Sandbox</h2>
                <p className="text-muted-foreground mt-1">
                    Test the classifier pipeline on any player and see step-by-step reasoning
                </p>
            </div>

            {/* Player Selection */}
            <Card>
                <CardHeader>
                    <CardTitle>Select Player</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* API Search */}
                    <div ref={searchRef} className="relative">
                        <Label className="text-sm font-medium">Search API-Football</Label>
                        <div className="relative mt-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                            <Input
                                value={searchQuery}
                                onChange={(e) => handleSearch(e.target.value)}
                                placeholder="Search by player name..."
                                className="pl-9"
                            />
                            {searching && (
                                <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-gray-400" />
                            )}
                        </div>
                        {showResults && searchResults.length > 0 && (
                            <div className="absolute z-10 w-full mt-1 bg-white border rounded-lg shadow-lg max-h-60 overflow-y-auto">
                                {searchResults.map((p) => (
                                    <button
                                        key={p.id}
                                        className="flex items-center gap-3 w-full px-3 py-2 hover:bg-gray-50 text-left"
                                        onClick={() => selectPlayer(p)}
                                    >
                                        {p.photo ? (
                                            <img src={p.photo} alt="" className="h-8 w-8 rounded-full object-cover" />
                                        ) : (
                                            <User className="h-8 w-8 p-1.5 rounded-full bg-gray-100 text-gray-400" />
                                        )}
                                        <div className="min-w-0 flex-1">
                                            <div className="text-sm font-medium truncate">{p.name}</div>
                                            <div className="text-xs text-gray-500">{p.team} | {p.nationality} | ID: {p.id}</div>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Tracked Player Picker */}
                    <div className="border-t pt-4">
                        <Label className="text-sm font-medium">Or select from tracked players</Label>
                        <div className="flex gap-2 mt-1">
                            <select
                                value={trackedTeamFilter}
                                onChange={(e) => setTrackedTeamFilter(e.target.value)}
                                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                            >
                                <option value="">All teams</option>
                                {trackedTeams.map((t) => (
                                    <option key={t.id} value={t.id}>{t.name}</option>
                                ))}
                            </select>
                            <select
                                value=""
                                onChange={(e) => {
                                    const tp = trackedPlayers.find((p) => p.id === parseInt(e.target.value))
                                    if (tp) selectTrackedPlayer(tp)
                                }}
                                className="h-9 flex-1 rounded-md border border-input bg-background px-3 text-sm"
                            >
                                <option value="">Choose player...</option>
                                {filteredTracked.map((tp) => (
                                    <option key={tp.id} value={tp.id}>
                                        {tp.player_name} ({tp.status}) — {tp.team?.name}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </div>

                    {/* Selected Player + Options */}
                    {selectedPlayer && (
                        <div className="border-t pt-4 space-y-3">
                            <div className="flex items-center gap-3 p-3 rounded-lg bg-blue-50 border border-blue-200">
                                {selectedPlayer.photo ? (
                                    <img src={selectedPlayer.photo} alt="" className="h-10 w-10 rounded-full object-cover" />
                                ) : (
                                    <User className="h-10 w-10 p-2 rounded-full bg-blue-100 text-blue-500" />
                                )}
                                <div>
                                    <div className="font-medium">{selectedPlayer.name}</div>
                                    <div className="text-xs text-gray-500">
                                        API ID: {selectedPlayer.id}
                                        {selectedPlayer.team && ` | ${selectedPlayer.team}`}
                                    </div>
                                </div>
                            </div>

                            <div className="flex flex-wrap items-end gap-4">
                                <div className="space-y-1">
                                    <Label className="text-xs">Parent Club Override (optional)</Label>
                                    <Input
                                        value={parentOverride}
                                        onChange={(e) => setParentOverride(e.target.value)}
                                        placeholder="API team ID e.g. 33"
                                        className="w-48"
                                    />
                                </div>
                                <label className="flex items-center gap-2 text-sm cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={forceSync}
                                        onChange={(e) => setForceSync(e.target.checked)}
                                        className="rounded border-gray-300"
                                    />
                                    Re-fetch from API
                                </label>
                                <Button onClick={runClassification} disabled={classifying}>
                                    {classifying ? (
                                        <>
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                            Classifying...
                                        </>
                                    ) : (
                                        'Run Classification'
                                    )}
                                </Button>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            {error && (
                <Alert className="border-red-500 bg-red-50">
                    <AlertCircle className="h-4 w-4 text-red-600" />
                    <AlertDescription className="text-red-800">{error}</AlertDescription>
                </Alert>
            )}

            {/* Results */}
            {result && (
                <>
                    {/* Player Info */}
                    <Card>
                        <CardContent className="pt-6">
                            <div className="flex items-center gap-4">
                                {result.player.photo ? (
                                    <img src={result.player.photo} alt="" className="h-16 w-16 rounded-full object-cover" />
                                ) : (
                                    <User className="h-16 w-16 p-4 rounded-full bg-gray-100 text-gray-400" />
                                )}
                                <div>
                                    <h3 className="text-xl font-bold">{result.player.name}</h3>
                                    <div className="text-sm text-gray-600">
                                        {result.player.nationality}
                                        {result.player.birth_date && ` | Born: ${result.player.birth_date}`}
                                    </div>
                                    <div className="text-sm text-gray-600 mt-0.5">
                                        Current: <span className="font-medium">{result.journey.current_club || 'Unknown'}</span>
                                        {result.journey.current_level && (
                                            <span className="text-xs ml-1 text-gray-500">({result.journey.current_level})</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Existing Tracked Status Diff */}
                    {result.existing_tracked?.length > 0 && (
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-base">Tracked Player Status</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    {result.existing_tracked.map((et, i) => (
                                        <div key={i} className="flex items-center gap-3 text-sm">
                                            <span className="text-gray-600">{et.parent_club_name}:</span>
                                            <StatusBadge status={et.current_status} />
                                            {et.would_change ? (
                                                <>
                                                    <ArrowRight className="h-4 w-4 text-orange-500" />
                                                    <StatusBadge status={et.new_status} />
                                                    <span className="text-xs text-orange-600 font-medium">CHANGED</span>
                                                </>
                                            ) : (
                                                <span className="text-xs text-green-600">no change</span>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Classifications */}
                    {result.classifications?.map((cls, idx) => (
                        <Card key={idx}>
                            <CardHeader
                                className="cursor-pointer"
                                onClick={() => setExpandedClassification(expandedClassification === idx ? null : idx)}
                            >
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <CardTitle className="text-base">
                                            Classification: {cls.parent_club_name}
                                        </CardTitle>
                                        <StatusBadge status={cls.status} />
                                        {cls.loan_club_name && (
                                            <span className="text-sm text-gray-500">
                                                at {cls.loan_club_name}
                                            </span>
                                        )}
                                    </div>
                                    {expandedClassification === idx
                                        ? <ChevronDown className="h-4 w-4 text-gray-400" />
                                        : <ChevronRight className="h-4 w-4 text-gray-400" />}
                                </div>
                            </CardHeader>
                            {expandedClassification === idx && (
                                <CardContent>
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-sm">
                                            <thead>
                                                <tr className="border-b text-left">
                                                    <th className="pb-2 pr-4 font-medium text-gray-500">Step</th>
                                                    <th className="pb-2 pr-4 font-medium text-gray-500">Rule</th>
                                                    <th className="pb-2 pr-4 font-medium text-gray-500">Check</th>
                                                    <th className="pb-2 pr-4 font-medium text-gray-500">Result</th>
                                                    <th className="pb-2 font-medium text-gray-500">Detail</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {cls.reasoning.map((r, ri) => (
                                                    <tr key={ri} className="border-b last:border-0">
                                                        <td className="py-2 pr-4 text-gray-400">{ri + 1}</td>
                                                        <td className="py-2 pr-4 font-mono text-xs">{r.rule}</td>
                                                        <td className="py-2 pr-4 text-gray-600 text-xs max-w-[200px] truncate" title={r.check}>{r.check}</td>
                                                        <td className="py-2 pr-4">
                                                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium border ${RESULT_COLORS[r.result] || ''}`}>
                                                                {r.result}
                                                            </span>
                                                        </td>
                                                        <td className="py-2 text-gray-700 text-xs">{r.detail}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </CardContent>
                            )}
                        </Card>
                    ))}

                    {/* Journey Timeline */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">
                                Journey ({result.journey.entries?.length || 0} entries, {result.journey.total_clubs} clubs)
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b text-left">
                                            <th className="pb-2 pr-3 font-medium text-gray-500">Season</th>
                                            <th className="pb-2 pr-3 font-medium text-gray-500">Club</th>
                                            <th className="pb-2 pr-3 font-medium text-gray-500">League</th>
                                            <th className="pb-2 pr-3 font-medium text-gray-500">Level</th>
                                            <th className="pb-2 pr-3 font-medium text-gray-500">Type</th>
                                            <th className="pb-2 pr-3 font-medium text-gray-500 text-right">Apps</th>
                                            <th className="pb-2 pr-3 font-medium text-gray-500 text-right">Goals</th>
                                            <th className="pb-2 font-medium text-gray-500 text-right">Mins</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(result.journey.entries || []).map((e, i) => (
                                            <tr key={i} className="border-b last:border-0">
                                                <td className="py-1.5 pr-3 font-mono text-xs">{e.season}</td>
                                                <td className="py-1.5 pr-3">
                                                    <div className="flex items-center gap-2">
                                                        {e.club_logo && <img src={e.club_logo} alt="" className="h-4 w-4" />}
                                                        <span className="truncate max-w-[150px]">{e.club_name}</span>
                                                    </div>
                                                </td>
                                                <td className="py-1.5 pr-3 text-gray-600 text-xs truncate max-w-[120px]">{e.league_name}</td>
                                                <td className="py-1.5 pr-3">
                                                    <span className={`text-xs ${e.is_youth ? 'text-blue-600' : e.is_international ? 'text-purple-600' : 'text-green-700'}`}>
                                                        {e.level}
                                                    </span>
                                                </td>
                                                <td className="py-1.5 pr-3 text-xs text-gray-500">{e.entry_type}</td>
                                                <td className="py-1.5 pr-3 text-right font-mono text-xs">{e.appearances || 0}</td>
                                                <td className="py-1.5 pr-3 text-right font-mono text-xs">{e.goals || 0}</td>
                                                <td className="py-1.5 text-right font-mono text-xs">{e.minutes || 0}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Transfer History */}
                    {result.transfer_summary?.length > 0 && (
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-base">Transfer History</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="border-b text-left">
                                                <th className="pb-2 pr-4 font-medium text-gray-500">Date</th>
                                                <th className="pb-2 pr-4 font-medium text-gray-500">From</th>
                                                <th className="pb-2 pr-4 font-medium text-gray-500">To</th>
                                                <th className="pb-2 font-medium text-gray-500">Type</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {result.transfer_summary.map((t, i) => (
                                                <tr key={i} className="border-b last:border-0">
                                                    <td className="py-1.5 pr-4 font-mono text-xs">{t.date || '—'}</td>
                                                    <td className="py-1.5 pr-4">{t.from || '—'}</td>
                                                    <td className="py-1.5 pr-4">{t.to || '—'}</td>
                                                    <td className="py-1.5 text-xs text-gray-600">{t.type || '—'}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </>
            )}
        </div>
    )
}
