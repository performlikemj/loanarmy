import { useState, useEffect } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { UserPlus, Search, AlertCircle, CheckCircle2, Trash2, RefreshCw } from 'lucide-react'
import TeamSelect from '@/components/ui/TeamSelect'

export function AdminPlayers() {
    // Teams for selection
    const [teams, setTeams] = useState([])
    // Players list
    const [players, setPlayers] = useState([])
    const [loadingPlayers, setLoadingPlayers] = useState(false)
    const [deletingId, setDeletingId] = useState(null)
    const [page, setPage] = useState(1)
    const [pageSize, setPageSize] = useState(20)
    const [totalPages, setTotalPages] = useState(1)

    // Add Player state
    const [showAddForm, setShowAddForm] = useState(false)
    const [addPlayerForm, setAddPlayerForm] = useState({
        name: '',
        firstname: '',
        lastname: '',
        position: '',
        nationality: '',
        age: '',
        sofascore_id: '',
        primary_team_id: '',
        loan_team_id: '',
        window_key: '',
        use_custom_primary_team: false,
        custom_primary_team_name: '',
        use_custom_loan_team: false,
        custom_loan_team_name: ''
    })

    // Message state
    const [message, setMessage] = useState(null)

    // Player field options
    const [playerFieldOptions, setPlayerFieldOptions] = useState({
        positions: ['Goalkeeper', 'Defender', 'Midfielder', 'Forward'],
        nationalities: ['England', 'Scotland', 'Wales', 'Ireland', 'France', 'Germany', 'Spain', 'Italy', 'Portugal', 'Netherlands', 'Belgium']
    })

    // Filters
    const [filters, setFilters] = useState({
        search: '',
        team_id: '',
        has_sofascore: 'any',
    })

    // Load teams
    useEffect(() => {
        const loadTeams = async () => {
            try {
                const teamsData = await APIService.getTeams()
                setTeams(teamsData || [])
            } catch (error) {
                console.error('Failed to load teams', error)
            }
        }
        loadTeams()
    }, [])

    // Load players list
    const loadPlayers = async (opts = {}) => {
        setLoadingPlayers(true)
        const nextPage = opts.page || page
        const nextPageSize = opts.pageSize || pageSize
        try {
            const params = {
                page: nextPage,
                page_size: nextPageSize,
                sort: '-updated_at',
            }
            if (filters.search.trim()) params.search = filters.search.trim()
            if (filters.team_id) params.team_id = Number(filters.team_id)
            if (filters.has_sofascore === 'true') params.has_sofascore = 'true'
            if (filters.has_sofascore === 'false') params.has_sofascore = 'false'

            const res = await APIService.adminPlayersList(params)
            setPlayers(res.items || [])
            setPage(res.page || 1)
            setPageSize(res.page_size || nextPageSize)
            setTotalPages(res.total_pages || 1)
        } catch (error) {
            console.error('Failed to load players', error)
            setMessage({ type: 'error', text: `Failed to load players: ${error?.body?.error || error.message}` })
        } finally {
            setLoadingPlayers(false)
        }
    }

    useEffect(() => {
        loadPlayers({ page: 1 })
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filters.search, filters.team_id, filters.has_sofascore])

    // Generate season options (last 3 years, next year)
    const generateSeasonOptions = () => {
        const currentYear = new Date().getFullYear()
        const seasons = []

        for (let year = currentYear + 1; year >= currentYear - 2; year--) {
            const nextYear = year + 1
            seasons.push({ value: `${year}-Summer`, label: `${year}/${nextYear} Summer` })
            seasons.push({ value: `${year}-Winter`, label: `${year}/${nextYear} Winter` })
        }

        return seasons
    }

    // Create player
    const createManualPlayer = async () => {
        if (!addPlayerForm.name.trim()) {
            setMessage({ type: 'error', text: 'Player name is required' })
            return
        }

        // Validate primary team
        if (!addPlayerForm.use_custom_primary_team && !addPlayerForm.primary_team_id) {
            setMessage({ type: 'error', text: 'Primary team is required (or check "Custom team")' })
            return
        }
        if (addPlayerForm.use_custom_primary_team && !addPlayerForm.custom_primary_team_name.trim()) {
            setMessage({ type: 'error', text: 'Custom primary team name is required' })
            return
        }

        // Validate loan team
        if (!addPlayerForm.use_custom_loan_team && !addPlayerForm.loan_team_id) {
            setMessage({ type: 'error', text: 'Loan team is required (or check "Custom team")' })
            return
        }
        if (addPlayerForm.use_custom_loan_team && !addPlayerForm.custom_loan_team_name.trim()) {
            setMessage({ type: 'error', text: 'Custom loan team name is required' })
            return
        }

        if (!addPlayerForm.window_key) {
            setMessage({ type: 'error', text: 'Season/window is required' })
            return
        }

        try {
            const payload = {
                name: addPlayerForm.name.trim(),
                firstname: addPlayerForm.firstname.trim() || null,
                lastname: addPlayerForm.lastname.trim() || null,
                position: addPlayerForm.position.trim() || null,
                nationality: addPlayerForm.nationality.trim() || null,
                age: addPlayerForm.age ? parseInt(addPlayerForm.age) : null,
                sofascore_id: addPlayerForm.sofascore_id ? parseInt(addPlayerForm.sofascore_id) : null,
                window_key: addPlayerForm.window_key
            }

            // Add primary team (either ID or custom name)
            if (addPlayerForm.use_custom_primary_team) {
                payload.custom_primary_team_name = addPlayerForm.custom_primary_team_name.trim()
            } else {
                payload.primary_team_id = parseInt(addPlayerForm.primary_team_id)
            }

            // Add loan team (either ID or custom name)
            if (addPlayerForm.use_custom_loan_team) {
                payload.custom_loan_team_name = addPlayerForm.custom_loan_team_name.trim()
            } else {
                payload.loan_team_id = parseInt(addPlayerForm.loan_team_id)
            }

            const result = await APIService.adminPlayerCreate(payload)
            setMessage({ type: 'success', text: result.message || `Player "${payload.name}" created successfully` })
            setShowAddForm(false)
            loadPlayers({ page: 1 })

            // Reset form
            setAddPlayerForm({
                name: '',
                firstname: '',
                lastname: '',
                position: '',
                nationality: '',
                age: '',
                sofascore_id: '',
                primary_team_id: '',
                loan_team_id: '',
                window_key: '',
                use_custom_primary_team: false,
                custom_primary_team_name: '',
                use_custom_loan_team: false,
                custom_loan_team_name: ''
            })
        } catch (error) {
            setMessage({ type: 'error', text: `Failed to create player: ${error?.body?.error || error.message}` })
        }
    }

    const deletePlayer = async (playerId, playerName) => {
        const confirmed = window.confirm(`Delete ${playerName || 'this player'} from tracking? This removes their loan rows and cached links.`)
        if (!confirmed) return
        setDeletingId(playerId)
        try {
            await APIService.adminPlayerDelete(playerId)
            setMessage({ type: 'success', text: `Deleted player ${playerName || playerId}` })
            setPlayers((prev) => prev.filter((p) => p.player_id !== playerId))
        } catch (error) {
            setMessage({ type: 'error', text: `Failed to delete: ${error?.body?.error || error.message}` })
        } finally {
            setDeletingId(null)
        }
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Players</h2>
                    <p className="text-muted-foreground mt-1">Add and manage loan players</p>
                </div>
                <Button onClick={() => setShowAddForm(!showAddForm)}>
                    <UserPlus className="h-4 w-4 mr-2" />
                    {showAddForm ? 'Cancel' : 'Add Player'}
                </Button>
            </div>

            {/* Message Display */}
            {message && (
                <Alert className={message.type === 'error' ? 'border-red-500 bg-red-50' : 'border-green-500 bg-green-50'}>
                    {message.type === 'error' ? <AlertCircle className="h-4 w-4 text-red-600" /> : <CheckCircle2 className="h-4 w-4 text-green-600" />}
                    <AlertDescription className={message.type === 'error' ? 'text-red-800' : 'text-green-800'}>
                        {message.text}
                    </AlertDescription>
                </Alert>
            )}

            {/* Add Player Form */}
            {showAddForm && (
                <Card className="border-green-200 bg-gradient-to-r from-green-50 to-blue-50">
                    <CardHeader>
                        <CardTitle>Create New Player</CardTitle>
                        <CardDescription>Add a player who didn't show up in the seeding process</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Player Name */}
                            <div className="md:col-span-2">
                                <Label htmlFor="player-name">Player Name *</Label>
                                <Input
                                    id="player-name"
                                    type="text"
                                    placeholder="Full name"
                                    value={addPlayerForm.name}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, name: e.target.value })}
                                />
                            </div>

                            {/* Primary Team */}
                            <div>
                                <div className="flex items-center justify-between mb-2">
                                    <Label>Primary Team (Parent Club) *</Label>
                                    <label className="flex items-center gap-1 text-xs text-muted-foreground cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={addPlayerForm.use_custom_primary_team}
                                            onChange={(e) => setAddPlayerForm({
                                                ...addPlayerForm,
                                                use_custom_primary_team: e.target.checked,
                                                primary_team_id: '',
                                                custom_primary_team_name: ''
                                            })}
                                            className="h-3 w-3"
                                        />
                                        Custom team
                                    </label>
                                </div>
                                {addPlayerForm.use_custom_primary_team ? (
                                    <Input
                                        type="text"
                                        placeholder="e.g. Portsmouth, Sunderland"
                                        value={addPlayerForm.custom_primary_team_name}
                                        onChange={(e) => setAddPlayerForm({ ...addPlayerForm, custom_primary_team_name: e.target.value })}
                                    />
                                ) : (
                                    <TeamSelect
                                        teams={teams}
                                        value={addPlayerForm.primary_team_id}
                                        onChange={(id) => setAddPlayerForm({ ...addPlayerForm, primary_team_id: id })}
                                        placeholder="Select primary team..."
                                    />
                                )}
                            </div>

                            {/* Loan Team */}
                            <div>
                                <div className="flex items-center justify-between mb-2">
                                    <Label>Loan Team (Current Club) *</Label>
                                    <label className="flex items-center gap-1 text-xs text-muted-foreground cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={addPlayerForm.use_custom_loan_team}
                                            onChange={(e) => setAddPlayerForm({
                                                ...addPlayerForm,
                                                use_custom_loan_team: e.target.checked,
                                                loan_team_id: '',
                                                custom_loan_team_name: ''
                                            })}
                                            className="h-3 w-3"
                                        />
                                        Custom team
                                    </label>
                                </div>
                                {addPlayerForm.use_custom_loan_team ? (
                                    <Input
                                        type="text"
                                        placeholder="e.g. Sheffield Wednesday, Hull City"
                                        value={addPlayerForm.custom_loan_team_name}
                                        onChange={(e) => setAddPlayerForm({ ...addPlayerForm, custom_loan_team_name: e.target.value })}
                                    />
                                ) : (
                                    <TeamSelect
                                        teams={teams}
                                        value={addPlayerForm.loan_team_id}
                                        onChange={(id) => setAddPlayerForm({ ...addPlayerForm, loan_team_id: id })}
                                        placeholder="Select loan team..."
                                    />
                                )}
                            </div>

                            {/* Season/Window */}
                            <div className="md:col-span-2">
                                <Label htmlFor="window">Season / Window *</Label>
                                <select
                                    id="window"
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    value={addPlayerForm.window_key}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, window_key: e.target.value })}
                                >
                                    <option value="">Select season...</option>
                                    {generateSeasonOptions().map(opt => (
                                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                </select>
                            </div>

                            {/* Position */}
                            <div>
                                <Label htmlFor="position">Position</Label>
                                <select
                                    id="position"
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    value={addPlayerForm.position}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, position: e.target.value })}
                                >
                                    <option value="">Select position...</option>
                                    {playerFieldOptions.positions.map(pos => (
                                        <option key={pos} value={pos}>{pos}</option>
                                    ))}
                                    <option value="__custom__">+ Add custom position</option>
                                </select>
                                {addPlayerForm.position === '__custom__' && (
                                    <Input
                                        type="text"
                                        placeholder="Enter custom position"
                                        onChange={(e) => setAddPlayerForm({ ...addPlayerForm, position: e.target.value })}
                                        className="mt-2"
                                        autoFocus
                                    />
                                )}
                            </div>

                            {/* Nationality */}
                            <div>
                                <Label htmlFor="nationality">Nationality</Label>
                                <select
                                    id="nationality"
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    value={addPlayerForm.nationality}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, nationality: e.target.value })}
                                >
                                    <option value="">Select nationality...</option>
                                    {playerFieldOptions.nationalities.map(nat => (
                                        <option key={nat} value={nat}>{nat}</option>
                                    ))}
                                    <option value="__custom__">+ Add custom nationality</option>
                                </select>
                                {addPlayerForm.nationality === '__custom__' && (
                                    <Input
                                        type="text"
                                        placeholder="Enter custom nationality"
                                        onChange={(e) => setAddPlayerForm({ ...addPlayerForm, nationality: e.target.value })}
                                        className="mt-2"
                                        autoFocus
                                    />
                                )}
                            </div>

                            {/* Age */}
                            <div>
                                <Label htmlFor="age">Age</Label>
                                <Input
                                    id="age"
                                    type="number"
                                    placeholder="Age"
                                    value={addPlayerForm.age}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, age: e.target.value })}
                                />
                            </div>

                            {/* Sofascore ID */}
                            <div>
                                <Label htmlFor="sofascore-id">Sofascore ID</Label>
                                <Input
                                    id="sofascore-id"
                                    type="number"
                                    placeholder="Optional Sofascore ID"
                                    value={addPlayerForm.sofascore_id}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, sofascore_id: e.target.value })}
                                />
                            </div>
                        </div>

                        {/* Form Actions */}
                        <div className="flex items-center gap-2 pt-2 border-t">
                            <Button onClick={createManualPlayer}>
                                Create Player
                            </Button>
                            <Button variant="outline" onClick={() => {
                                setShowAddForm(false)
                                setAddPlayerForm({
                                    name: '',
                                    firstname: '',
                                    lastname: '',
                                    position: '',
                                    nationality: '',
                                    age: '',
                                    sofascore_id: '',
                                    primary_team_id: '',
                                    loan_team_id: '',
                                    window_key: '',
                                    use_custom_primary_team: false,
                                    custom_primary_team_name: '',
                                    use_custom_loan_team: false,
                                    custom_loan_team_name: ''
                                })
                            }}>
                                Cancel
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Tracked players with delete controls */}
            <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                    <div>
                        <CardTitle>Tracked Players</CardTitle>
                        <CardDescription>Remove a player to re-seed or clean up tracking</CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                        <Input
                            placeholder="Search player name"
                            className="h-9 w-48"
                            value={filters.search}
                            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
                        />
                        <TeamSelect
                            teams={teams}
                            value={filters.team_id}
                            placeholder="Filter by team..."
                            onChange={(id) => setFilters({ ...filters, team_id: id })}
                            className="min-w-[180px]"
                        />
                        <select
                            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                            value={filters.has_sofascore}
                            onChange={(e) => setFilters({ ...filters, has_sofascore: e.target.value })}
                        >
                            <option value="any">All</option>
                            <option value="true">With Sofascore ID</option>
                            <option value="false">Without Sofascore ID</option>
                        </select>
                        <Button variant="outline" size="sm" onClick={() => loadPlayers({ page: 1 })} disabled={loadingPlayers}>
                            {loadingPlayers ? (
                                <span className="flex items-center gap-1">
                                    <RefreshCw className="h-4 w-4 animate-spin" /> Refreshing…
                                </span>
                            ) : (
                                <span className="flex items-center gap-1">
                                    <RefreshCw className="h-4 w-4" /> Refresh
                                </span>
                            )}
                        </Button>
                    </div>
                </CardHeader>
                <CardContent className="space-y-3">
                    {loadingPlayers && <p className="text-sm text-muted-foreground">Loading players…</p>}
                    {!loadingPlayers && players.length === 0 && (
                        <p className="text-sm text-muted-foreground">No players tracked yet.</p>
                    )}
                    {!loadingPlayers && players.length > 0 && (
                        <div className="space-y-2">
                            {players.map((p) => (
                                <div
                                    key={p.player_id}
                                    className="flex flex-col gap-1 rounded-md border px-3 py-2 md:flex-row md:items-center md:justify-between"
                                >
                                    <div>
                                        <div className="font-medium">{p.player_name || p.name || 'Unknown player'}</div>
                                        <div className="text-xs text-muted-foreground">
                                            ID: {p.player_id} • Parent: {p.primary_team_name || '—'} • Loan: {p.loan_team_name || '—'} • Season: {p.window_key || '—'}
                                        </div>
                                    </div>
                                    <Button
                                        variant="destructive"
                                        size="sm"
                                        disabled={deletingId === p.player_id}
                                        onClick={() => deletePlayer(p.player_id, p.player_name || p.name)}
                                    >
                                        {deletingId === p.player_id ? (
                                            <span className="flex items-center gap-1">
                                                <Trash2 className="h-4 w-4 animate-pulse" /> Deleting…
                                            </span>
                                        ) : (
                                            <span className="flex items-center gap-1">
                                                <Trash2 className="h-4 w-4" /> Delete
                                            </span>
                                        )}
                                    </Button>
                                </div>
                            ))}
                        </div>
                    )}
                    {/* Pagination */}
                    {!loadingPlayers && players.length > 0 && (
                        <div className="flex items-center justify-between pt-2">
                            <div className="text-xs text-muted-foreground">
                                Page {page} of {totalPages}
                            </div>
                            <div className="flex items-center gap-2">
                                <select
                                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                                    value={pageSize}
                                    onChange={(e) => {
                                        const size = Number(e.target.value) || 20
                                        setPageSize(size)
                                        setPage(1)
                                        loadPlayers({ page: 1, pageSize: size })
                                    }}
                                >
                                    {[10, 20, 50, 100].map((n) => (
                                        <option key={n} value={n}>{n} / page</option>
                                    ))}
                                </select>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={page <= 1}
                                    onClick={() => {
                                        const next = Math.max(1, page - 1)
                                        setPage(next)
                                        loadPlayers({ page: next })
                                    }}
                                >
                                    Prev
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={page >= totalPages}
                                    onClick={() => {
                                        const next = Math.min(totalPages, page + 1)
                                        setPage(next)
                                        loadPlayers({ page: next })
                                    }}
                                >
                                    Next
                                </Button>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Info Card */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Search className="h-5 w-5" />
                        Player Management
                    </CardTitle>
                    <CardDescription>
                        Use the form above to add players who didn't appear in the seeding process.
                        For comprehensive player search and editing, use the full admin tools.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="rounded-lg border border-dashed bg-muted/40 p-6 text-sm text-muted-foreground space-y-2">
                        <p><strong>Tip:</strong> After seeding teams, some loan players may not appear automatically. Use the "+ Add Player" button to manually add them.</p>
                        <p><strong>Custom Teams:</strong> If a team isn't in the dropdown, check the "Custom team" option to enter the team name manually.</p>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
