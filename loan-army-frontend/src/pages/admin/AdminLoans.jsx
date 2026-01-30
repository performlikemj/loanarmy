import { useState, useEffect } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Trophy, Search, AlertCircle, CheckCircle2, Filter, Pencil, X, Save, Power, ArrowRightLeft, RefreshCw, CheckSquare, Square } from 'lucide-react'
import TeamSelect from '@/components/ui/TeamSelect'

export function AdminLoans() {
    // State
    const [loans, setLoans] = useState([])
    const [teams, setTeams] = useState([])
    const [loading, setLoading] = useState(false)
    const [message, setMessage] = useState(null)

    // Edit state
    const [editingLoanId, setEditingLoanId] = useState(null)
    const [editForm, setEditForm] = useState({
        primary_team_db_id: '',
        loan_team_db_id: '',
        is_active: true,
        pathway_status: 'on_loan',
        current_level: ''
    })
    const [saving, setSaving] = useState(false)

    // Transition modal state
    const [transitionLoan, setTransitionLoan] = useState(null)
    const [transitionForm, setTransitionForm] = useState({
        new_loan_team_db_id: '',
        new_loan_team_name: '',
        deactivate_only: false
    })
    const [transitioning, setTransitioning] = useState(false)

    // Bulk selection state
    const [selectMode, setSelectMode] = useState(false)
    const [selectedLoans, setSelectedLoans] = useState(new Set())
    const [bulkAction, setBulkAction] = useState(null) // 'deactivate' | 'transition'
    const [bulkProcessing, setBulkProcessing] = useState(false)
    const [bulkTransitionTeam, setBulkTransitionTeam] = useState({ db_id: '', name: '' })

    // Preview sync state
    const [showPreviewSync, setShowPreviewSync] = useState(false)
    const [previewSyncLoading, setPreviewSyncLoading] = useState(false)
    const [previewSyncData, setPreviewSyncData] = useState(null)
    const [previewSyncSeason, setPreviewSyncSeason] = useState(2025)
    const [previewSyncTeamId, setPreviewSyncTeamId] = useState('')
    const [seedingTeam, setSeedingTeam] = useState(false)

    // Filters
    const [filters, setFilters] = useState({
        active_only: 'true',
        primary_team_db_id: '',
        player_name: '',
        data_source: '', // '', 'manual', 'api-football'
        pathway_status: '' // '', 'academy', 'on_loan', 'first_team', 'released'
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

    // Load loans
    const loadLoans = async () => {
        setLoading(true)
        setMessage(null)
        try {
            const data = await APIService.adminLoansList(filters)
            setLoans(Array.isArray(data) ? data : [])
        } catch (error) {
            console.error('Failed to load loans', error)
            setMessage({ type: 'error', text: 'Failed to load loans' })
        } finally {
            setLoading(false)
        }
    }

    // Load on mount
    useEffect(() => {
        loadLoans()
    }, []) // eslint-disable-line react-hooks/exhaustive-deps

    const applyFilters = () => {
        loadLoans()
    }

    const resetFilters = () => {
        setFilters({
            active_only: 'true',
            primary_team_db_id: '',
            player_name: '',
            data_source: '',
            pathway_status: ''
        })
    }

    // Start editing a loan
    const startEdit = (loan) => {
        setEditingLoanId(loan.id)
        setEditForm({
            primary_team_db_id: loan.primary_team_id || '',
            loan_team_db_id: loan.loan_team_id || '',
            is_active: loan.is_active,
            pathway_status: loan.pathway_status || 'on_loan',
            current_level: loan.current_level || ''
        })
        setMessage(null)
    }

    // Cancel editing
    const cancelEdit = () => {
        setEditingLoanId(null)
        setEditForm({
            primary_team_db_id: '',
            loan_team_db_id: '',
            is_active: true,
            pathway_status: 'on_loan',
            current_level: ''
        })
    }

    // Save edited loan
    const saveEdit = async () => {
        if (!editingLoanId) return

        setSaving(true)
        setMessage(null)
        try {
            const payload = {
                primary_team_db_id: editForm.primary_team_db_id || undefined,
                loan_team_db_id: editForm.loan_team_db_id || undefined,
                is_active: editForm.is_active,
                pathway_status: editForm.pathway_status,
                current_level: editForm.current_level || null
            }
            await APIService.adminLoanUpdate(editingLoanId, payload)

            // Update loan in state directly instead of reloading
            setLoans(prev => prev.map(loan => {
                if (loan.id !== editingLoanId) return loan
                const primaryTeam = teams.find(t => t.id === parseInt(editForm.primary_team_db_id))
                const loanTeam = teams.find(t => t.id === parseInt(editForm.loan_team_db_id))
                return {
                    ...loan,
                    primary_team_id: editForm.primary_team_db_id ? parseInt(editForm.primary_team_db_id) : loan.primary_team_id,
                    primary_team_name: primaryTeam?.name || loan.primary_team_name,
                    loan_team_id: editForm.loan_team_db_id ? parseInt(editForm.loan_team_db_id) : loan.loan_team_id,
                    loan_team_name: loanTeam?.name || loan.loan_team_name,
                    is_active: editForm.is_active,
                    pathway_status: editForm.pathway_status,
                    current_level: editForm.current_level || null
                }
            }))

            setMessage({ type: 'success', text: 'Loan updated successfully' })
            cancelEdit()
        } catch (error) {
            console.error('Failed to update loan', error)
            setMessage({ type: 'error', text: error?.body?.error || 'Failed to update loan' })
        } finally {
            setSaving(false)
        }
    }

    // Quick deactivate a loan
    const deactivateLoan = async (loanId) => {
        if (!window.confirm('Deactivate this loan? This marks the loan as no longer active.')) return

        try {
            await APIService.adminLoanDeactivate(loanId)

            // Update loan in state directly
            setLoans(prev => prev.map(loan =>
                loan.id === loanId ? { ...loan, is_active: false } : loan
            ))

            setMessage({ type: 'success', text: 'Loan deactivated' })
        } catch (error) {
            console.error('Failed to deactivate loan', error)
            setMessage({ type: 'error', text: error?.body?.error || 'Failed to deactivate loan' })
        }
    }

    // Open transition modal
    const openTransition = (loan) => {
        setTransitionLoan(loan)
        setTransitionForm({
            new_loan_team_db_id: '',
            new_loan_team_name: '',
            deactivate_only: false
        })
    }

    // Handle transition
    const handleTransition = async () => {
        if (!transitionLoan) return

        setTransitioning(true)
        try {
            const payload = {
                deactivate_only: transitionForm.deactivate_only
            }
            if (!transitionForm.deactivate_only) {
                if (transitionForm.new_loan_team_db_id) {
                    payload.new_loan_team_db_id = parseInt(transitionForm.new_loan_team_db_id)
                } else if (transitionForm.new_loan_team_name) {
                    payload.new_loan_team_name = transitionForm.new_loan_team_name
                } else {
                    setMessage({ type: 'error', text: 'Select a new loan team or enter a custom team name' })
                    setTransitioning(false)
                    return
                }
            }

            const result = await APIService.adminLoanTransition(transitionLoan.id, payload)

            // Update state directly - mark old loan inactive and add new loan if created
            setLoans(prev => {
                let updated = prev.map(loan =>
                    loan.id === transitionLoan.id ? { ...loan, is_active: false } : loan
                )

                // If a new loan was created, add it to the list
                if (result.new_loan_id && !transitionForm.deactivate_only) {
                    const newLoanTeam = teams.find(t => t.id === parseInt(transitionForm.new_loan_team_db_id))
                    const newLoan = {
                        id: result.new_loan_id,
                        player_id: transitionLoan.player_id,
                        player_name: transitionLoan.player_name,
                        primary_team_id: transitionLoan.primary_team_id,
                        primary_team_name: transitionLoan.primary_team_name,
                        loan_team_id: newLoanTeam?.id || null,
                        loan_team_name: result.new_loan_team || newLoanTeam?.name || transitionForm.new_loan_team_name,
                        is_active: true,
                        data_source: 'manual',
                        window_key: transitionLoan.window_key
                    }
                    updated = [newLoan, ...updated]
                }

                return updated
            })

            setMessage({ type: 'success', text: transitionForm.deactivate_only
                ? 'Loan ended successfully'
                : `Player transitioned to ${transitionForm.new_loan_team_db_id ? teams.find(t => t.id === parseInt(transitionForm.new_loan_team_db_id))?.name : transitionForm.new_loan_team_name}`
            })
            setTransitionLoan(null)
        } catch (error) {
            console.error('Failed to transition loan', error)
            setMessage({ type: 'error', text: error?.body?.error || 'Failed to transition loan' })
        } finally {
            setTransitioning(false)
        }
    }

    // Bulk selection handlers
    const toggleSelectMode = () => {
        setSelectMode(!selectMode)
        setSelectedLoans(new Set())
        setBulkAction(null)
    }

    const toggleLoanSelection = (loanId) => {
        const newSelected = new Set(selectedLoans)
        if (newSelected.has(loanId)) {
            newSelected.delete(loanId)
        } else {
            newSelected.add(loanId)
        }
        setSelectedLoans(newSelected)
    }

    const selectAll = () => {
        const activeLoans = loans.filter(l => l.is_active)
        setSelectedLoans(new Set(activeLoans.map(l => l.id)))
    }

    const clearSelection = () => {
        setSelectedLoans(new Set())
        setBulkAction(null)
    }

    // Bulk deactivate
    const handleBulkDeactivate = async () => {
        if (selectedLoans.size === 0) return
        if (!window.confirm(`Deactivate ${selectedLoans.size} loan(s)?`)) return

        setBulkProcessing(true)
        try {
            const loanIds = Array.from(selectedLoans)
            await APIService.adminLoansBulkDeactivate(loanIds)

            // Update state directly - mark all selected loans as inactive
            setLoans(prev => prev.map(loan =>
                loanIds.includes(loan.id) ? { ...loan, is_active: false } : loan
            ))

            setMessage({ type: 'success', text: `${selectedLoans.size} loan(s) deactivated` })
            clearSelection()
            setSelectMode(false)
        } catch (error) {
            console.error('Failed to bulk deactivate', error)
            setMessage({ type: 'error', text: error?.body?.error || 'Failed to bulk deactivate' })
        } finally {
            setBulkProcessing(false)
        }
    }

    // Bulk transition
    const handleBulkTransition = async () => {
        if (selectedLoans.size === 0) return
        if (!bulkTransitionTeam.db_id && !bulkTransitionTeam.name) {
            setMessage({ type: 'error', text: 'Select a team or enter a custom team name' })
            return
        }

        setBulkProcessing(true)
        try {
            const loanIds = Array.from(selectedLoans)
            const transitions = loanIds.map(loanId => ({
                loan_id: loanId,
                new_loan_team_db_id: bulkTransitionTeam.db_id ? parseInt(bulkTransitionTeam.db_id) : undefined,
                new_loan_team_name: bulkTransitionTeam.name || undefined
            }))
            const result = await APIService.adminLoansBulkTransition(transitions)

            // Update state directly - mark old loans inactive and add new ones
            setLoans(prev => {
                // Mark selected loans as inactive
                let updated = prev.map(loan =>
                    loanIds.includes(loan.id) ? { ...loan, is_active: false } : loan
                )

                // Add new loans from the response
                const newLoans = (result.details || [])
                    .filter(d => d.status === 'transitioned' && d.new_loan_id)
                    .map(d => ({
                        id: d.new_loan_id,
                        player_id: d.player_id,
                        player_name: d.player_name,
                        primary_team_id: d.primary_team_id,
                        primary_team_name: d.primary_team_name,
                        loan_team_id: bulkTransitionTeam.db_id ? parseInt(bulkTransitionTeam.db_id) : null,
                        loan_team_name: d.new_loan_team,
                        is_active: true,
                        data_source: 'manual',
                        window_key: d.window_key
                    }))

                return [...newLoans, ...updated]
            })

            setMessage({ type: 'success', text: `${result.transitioned || 0} loan(s) transitioned` })
            clearSelection()
            setBulkAction(null)
            setSelectMode(false)
        } catch (error) {
            console.error('Failed to bulk transition', error)
            setMessage({ type: 'error', text: error?.body?.error || 'Failed to bulk transition' })
        } finally {
            setBulkProcessing(false)
        }
    }

    // Preview sync
    const handlePreviewSync = async () => {
        setPreviewSyncLoading(true)
        try {
            const params = {
                season: previewSyncSeason
            }
            if (previewSyncTeamId) {
                params.team_db_id = parseInt(previewSyncTeamId)
            }
            const data = await APIService.adminLoansPreviewSync(params)
            setPreviewSyncData(data)
        } catch (error) {
            console.error('Failed to preview sync', error)
            setMessage({ type: 'error', text: error?.body?.error || 'Failed to preview sync' })
        } finally {
            setPreviewSyncLoading(false)
        }
    }

    // Seed team from preview sync
    const handleSeedTeam = async () => {
        if (!previewSyncTeamId) {
            setMessage({ type: 'error', text: 'Please select a team first' })
            return
        }
        setSeedingTeam(true)
        try {
            const params = {
                season: previewSyncSeason,
                team_db_id: parseInt(previewSyncTeamId)
            }
            const result = await APIService.adminSeedTeam(params)
            setMessage({ type: 'success', text: `Seeded ${result.created || 0} loans for team (${result.skipped || 0} skipped)` })

            // Clear preview data to prompt re-check
            setPreviewSyncData(null)

            // Only reload if loans were actually created
            if (result.created > 0) {
                loadLoans()
            }
        } catch (error) {
            console.error('Failed to seed team', error)
            setMessage({ type: 'error', text: error?.body?.error || 'Failed to seed team' })
        } finally {
            setSeedingTeam(false)
        }
    }

    // Get data source badge
    const getDataSourceBadge = (loan) => {
        if (loan.data_source === 'manual') {
            return (
                <Badge variant="outline" className="text-purple-600 border-purple-300 text-xs">
                    Manual
                </Badge>
            )
        }
        if (loan.api_confirmed_at) {
            return (
                <Badge variant="outline" className="text-green-600 border-green-300 text-xs">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    API Confirmed
                </Badge>
            )
        }
        return null
    }

    // Get pathway status badge
    const getPathwayBadge = (loan) => {
        const status = loan.pathway_status || 'on_loan'
        const level = loan.current_level

        const statusConfig = {
            academy: { color: 'text-blue-600 border-blue-300 bg-blue-50', label: 'Academy' },
            on_loan: { color: 'text-amber-600 border-amber-300 bg-amber-50', label: 'On Loan' },
            first_team: { color: 'text-emerald-600 border-emerald-300 bg-emerald-50', label: 'First Team' },
            released: { color: 'text-gray-500 border-gray-300 bg-gray-50', label: 'Released' }
        }

        const config = statusConfig[status] || statusConfig.on_loan
        const label = level ? `${config.label} (${level})` : config.label

        return (
            <Badge variant="outline" className={`${config.color} text-xs`}>
                {label}
            </Badge>
        )
    }

    // Filter loans by data_source and pathway_status if set
    const filteredLoans = loans.filter(l => {
        if (filters.data_source && l.data_source !== filters.data_source) return false
        if (filters.pathway_status && (l.pathway_status || 'on_loan') !== filters.pathway_status) return false
        return true
    })

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Loans</h2>
                    <p className="text-muted-foreground mt-1">View and manage loan records</p>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant={selectMode ? "default" : "outline"}
                        onClick={toggleSelectMode}
                    >
                        {selectMode ? <CheckSquare className="h-4 w-4 mr-2" /> : <Square className="h-4 w-4 mr-2" />}
                        {selectMode ? 'Exit Select' : 'Select Mode'}
                    </Button>
                    <Button
                        variant="outline"
                        onClick={() => setShowPreviewSync(true)}
                    >
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Preview Sync
                    </Button>
                    <Button onClick={loadLoans} disabled={loading}>
                        <Trophy className="h-4 w-4 mr-2" />
                        Refresh
                    </Button>
                </div>
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

            {/* Bulk Action Toolbar */}
            {selectMode && selectedLoans.size > 0 && (
                <Card className="border-blue-300 bg-blue-50">
                    <CardContent className="py-3">
                        <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-blue-800">
                                {selectedLoans.size} loan(s) selected
                            </span>
                            <div className="flex items-center gap-2">
                                {bulkAction === 'transition' ? (
                                    <>
                                        <TeamSelect
                                            teams={teams}
                                            value={bulkTransitionTeam.db_id}
                                            onChange={(id) => setBulkTransitionTeam({ ...bulkTransitionTeam, db_id: id, name: '' })}
                                            placeholder="Select new team..."
                                            className="w-48"
                                        />
                                        <span className="text-sm text-muted-foreground">or</span>
                                        <Input
                                            type="text"
                                            placeholder="Custom team name..."
                                            value={bulkTransitionTeam.name}
                                            onChange={(e) => setBulkTransitionTeam({ ...bulkTransitionTeam, name: e.target.value, db_id: '' })}
                                            className="w-40"
                                        />
                                        <Button size="sm" onClick={handleBulkTransition} disabled={bulkProcessing}>
                                            {bulkProcessing ? 'Processing...' : 'Confirm'}
                                        </Button>
                                        <Button size="sm" variant="outline" onClick={() => setBulkAction(null)}>
                                            Cancel
                                        </Button>
                                    </>
                                ) : (
                                    <>
                                        <Button
                                            size="sm"
                                            variant="destructive"
                                            onClick={handleBulkDeactivate}
                                            disabled={bulkProcessing}
                                        >
                                            <Power className="h-4 w-4 mr-1" />
                                            Deactivate Selected
                                        </Button>
                                        <Button
                                            size="sm"
                                            onClick={() => setBulkAction('transition')}
                                        >
                                            <ArrowRightLeft className="h-4 w-4 mr-1" />
                                            Transition Selected
                                        </Button>
                                        <Button size="sm" variant="outline" onClick={clearSelection}>
                                            Clear
                                        </Button>
                                    </>
                                )}
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Filters */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <Filter className="h-5 w-5" />
                                Filters
                            </CardTitle>
                            <CardDescription>Filter loan records by team, status, or search</CardDescription>
                        </div>
                        <div className="flex gap-2">
                            <Button size="sm" onClick={applyFilters}>Apply</Button>
                            <Button size="sm" variant="outline" onClick={resetFilters}>Reset</Button>
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                        <div>
                            <Label htmlFor="status-filter">Status</Label>
                            <select
                                id="status-filter"
                                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
                                value={filters.active_only}
                                onChange={(e) => setFilters({ ...filters, active_only: e.target.value })}
                            >
                                <option value="true">Active Only</option>
                                <option value="false">All Loans</option>
                            </select>
                        </div>
                        <div>
                            <Label htmlFor="team-filter">Team</Label>
                            <TeamSelect
                                teams={teams}
                                value={filters.primary_team_db_id}
                                onChange={(id) => setFilters({ ...filters, primary_team_db_id: id })}
                                placeholder="Filter by team..."
                            />
                        </div>
                        <div>
                            <Label htmlFor="pathway-filter">Pathway</Label>
                            <select
                                id="pathway-filter"
                                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
                                value={filters.pathway_status}
                                onChange={(e) => setFilters({ ...filters, pathway_status: e.target.value })}
                            >
                                <option value="">All Pathways</option>
                                <option value="academy">Academy</option>
                                <option value="on_loan">On Loan</option>
                                <option value="first_team">First Team</option>
                                <option value="released">Released</option>
                            </select>
                        </div>
                        <div>
                            <Label htmlFor="source-filter">Source</Label>
                            <select
                                id="source-filter"
                                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
                                value={filters.data_source}
                                onChange={(e) => setFilters({ ...filters, data_source: e.target.value })}
                            >
                                <option value="">All Sources</option>
                                <option value="manual">Manual Only</option>
                                <option value="api-football">API Only</option>
                            </select>
                        </div>
                        <div>
                            <Label htmlFor="search-filter">Search</Label>
                            <Input
                                id="search-filter"
                                type="text"
                                placeholder="Player name..."
                                value={filters.player_name}
                                onChange={(e) => setFilters({ ...filters, player_name: e.target.value })}
                                onKeyPress={(e) => e.key === 'Enter' && applyFilters()}
                            />
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Loans List */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle>Loan Records ({filteredLoans.length})</CardTitle>
                            <CardDescription>
                                {filters.active_only === 'true' ? 'Showing active loans only' : 'Showing all loan records'}
                            </CardDescription>
                        </div>
                        {selectMode && (
                            <Button size="sm" variant="outline" onClick={selectAll}>
                                Select All Active
                            </Button>
                        )}
                    </div>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="text-center py-8 text-muted-foreground">
                            Loading loans...
                        </div>
                    ) : filteredLoans.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <Trophy className="h-12 w-12 mx-auto mb-3 opacity-50" />
                            <p>No loans found</p>
                            <p className="text-sm mt-1">Try adjusting your filters or seed loan data from the Newsletters page</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {filteredLoans.map((loan) => (
                                <div
                                    key={loan.id}
                                    className={`border rounded-lg p-4 transition-colors ${editingLoanId === loan.id ? 'border-blue-300 bg-blue-50/50' : selectedLoans.has(loan.id) ? 'border-blue-400 bg-blue-50' : 'hover:bg-accent/50'}`}
                                >
                                    {editingLoanId === loan.id ? (
                                        // Edit mode
                                        <div className="space-y-4">
                                            <div className="flex items-center justify-between">
                                                <h3 className="font-semibold">{loan.player_name || 'Unknown Player'}</h3>
                                                <Badge variant="outline" className="text-blue-600 border-blue-300">
                                                    Editing
                                                </Badge>
                                            </div>

                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                <div>
                                                    <Label className="text-sm font-medium">Parent Club</Label>
                                                    <TeamSelect
                                                        teams={teams}
                                                        value={editForm.primary_team_db_id}
                                                        onChange={(id) => setEditForm({ ...editForm, primary_team_db_id: id })}
                                                        placeholder="Select parent club..."
                                                    />
                                                </div>
                                                <div>
                                                    <Label className="text-sm font-medium">Loan Club</Label>
                                                    <TeamSelect
                                                        teams={teams}
                                                        value={editForm.loan_team_db_id}
                                                        onChange={(id) => setEditForm({ ...editForm, loan_team_db_id: id })}
                                                        placeholder="Select loan club..."
                                                    />
                                                </div>
                                            </div>

                                            {/* Pathway Tracking */}
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                <div>
                                                    <Label className="text-sm font-medium">Pathway Status</Label>
                                                    <select
                                                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
                                                        value={editForm.pathway_status}
                                                        onChange={(e) => setEditForm({ ...editForm, pathway_status: e.target.value })}
                                                    >
                                                        <option value="on_loan">On Loan</option>
                                                        <option value="academy">Academy</option>
                                                        <option value="first_team">First Team</option>
                                                        <option value="released">Released</option>
                                                    </select>
                                                </div>
                                                <div>
                                                    <Label className="text-sm font-medium">Current Level</Label>
                                                    <select
                                                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
                                                        value={editForm.current_level}
                                                        onChange={(e) => setEditForm({ ...editForm, current_level: e.target.value })}
                                                    >
                                                        <option value="">Not Set</option>
                                                        <option value="U18">U18</option>
                                                        <option value="U21">U21</option>
                                                        <option value="U23">U23</option>
                                                        <option value="Reserve">Reserve</option>
                                                        <option value="Senior">Senior</option>
                                                    </select>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-2">
                                                <label className="flex items-center gap-2 cursor-pointer">
                                                    <input
                                                        type="checkbox"
                                                        checked={editForm.is_active}
                                                        onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                                                        className="h-4 w-4 rounded border-gray-300"
                                                    />
                                                    <span className="text-sm">Active loan</span>
                                                </label>
                                            </div>

                                            <div className="flex items-center gap-2 pt-2 border-t">
                                                <Button size="sm" onClick={saveEdit} disabled={saving}>
                                                    <Save className="h-4 w-4 mr-1" />
                                                    {saving ? 'Saving...' : 'Save'}
                                                </Button>
                                                <Button size="sm" variant="outline" onClick={cancelEdit} disabled={saving}>
                                                    <X className="h-4 w-4 mr-1" />
                                                    Cancel
                                                </Button>
                                            </div>
                                        </div>
                                    ) : (
                                        // View mode
                                        <div className="flex items-start justify-between">
                                            <div className="flex items-start gap-3">
                                                {selectMode && (
                                                    <button
                                                        onClick={() => toggleLoanSelection(loan.id)}
                                                        className="mt-1"
                                                    >
                                                        {selectedLoans.has(loan.id) ? (
                                                            <CheckSquare className="h-5 w-5 text-blue-600" />
                                                        ) : (
                                                            <Square className="h-5 w-5 text-muted-foreground" />
                                                        )}
                                                    </button>
                                                )}
                                                <div className="space-y-1 flex-1">
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                        <h3 className="font-semibold">{loan.player_name || 'Unknown Player'}</h3>
                                                        {loan.is_active ? (
                                                            <Badge variant="default" className="bg-green-100 text-green-800 border-green-300">
                                                                Active
                                                            </Badge>
                                                        ) : (
                                                            <Badge variant="secondary" className="text-muted-foreground">
                                                                Inactive
                                                            </Badge>
                                                        )}
                                                        {getPathwayBadge(loan)}
                                                        {getDataSourceBadge(loan)}
                                                    </div>
                                                    <div className="text-sm text-muted-foreground space-y-0.5">
                                                        <p>
                                                            <strong>From:</strong> {loan.primary_team_name || 'Unknown'}
                                                            <span className="mx-2">→</span>
                                                            <strong>To:</strong> {loan.loan_team_name || 'Unknown'}
                                                        </p>
                                                        {loan.window_key && (
                                                            <p><strong>Window:</strong> {loan.window_key}</p>
                                                        )}
                                                        {loan.position && (
                                                            <p><strong>Position:</strong> {loan.position}</p>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                            {!selectMode && (
                                                <div className="flex items-center gap-1">
                                                    <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={() => startEdit(loan)}
                                                        title="Edit loan"
                                                    >
                                                        <Pencil className="h-4 w-4" />
                                                    </Button>
                                                    {loan.is_active && (
                                                        <>
                                                            <Button
                                                                size="sm"
                                                                variant="ghost"
                                                                onClick={() => openTransition(loan)}
                                                                title="Transition to new club"
                                                                className="text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                                                            >
                                                                <ArrowRightLeft className="h-4 w-4" />
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                variant="ghost"
                                                                onClick={() => deactivateLoan(loan.id)}
                                                                title="Deactivate loan"
                                                                className="text-orange-600 hover:text-orange-700 hover:bg-orange-50"
                                                            >
                                                                <Power className="h-4 w-4" />
                                                            </Button>
                                                        </>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Transition Modal */}
            {transitionLoan && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <Card className="w-full max-w-md mx-4">
                        <CardHeader>
                            <CardTitle>Transition Loan</CardTitle>
                            <CardDescription>
                                End current loan and optionally move {transitionLoan.player_name} to a new club
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="p-3 bg-muted rounded-lg text-sm">
                                <p><strong>Current:</strong> {transitionLoan.primary_team_name} → {transitionLoan.loan_team_name}</p>
                            </div>

                            <div className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="deactivate-only"
                                    checked={transitionForm.deactivate_only}
                                    onChange={(e) => setTransitionForm({ ...transitionForm, deactivate_only: e.target.checked })}
                                    className="h-4 w-4 rounded border-gray-300"
                                />
                                <label htmlFor="deactivate-only" className="text-sm">
                                    Just end the loan (don't create new)
                                </label>
                            </div>

                            {!transitionForm.deactivate_only && (
                                <>
                                    <div>
                                        <Label>New Loan Club</Label>
                                        <TeamSelect
                                            teams={teams}
                                            value={transitionForm.new_loan_team_db_id}
                                            onChange={(id) => setTransitionForm({ ...transitionForm, new_loan_team_db_id: id, new_loan_team_name: '' })}
                                            placeholder="Select new club..."
                                        />
                                    </div>
                                    <div>
                                        <Label className="text-muted-foreground text-sm">Or enter custom team name</Label>
                                        <Input
                                            type="text"
                                            placeholder="Custom team name..."
                                            value={transitionForm.new_loan_team_name}
                                            onChange={(e) => setTransitionForm({ ...transitionForm, new_loan_team_name: e.target.value, new_loan_team_db_id: '' })}
                                        />
                                    </div>
                                </>
                            )}

                            <div className="flex justify-end gap-2 pt-4 border-t">
                                <Button variant="outline" onClick={() => setTransitionLoan(null)} disabled={transitioning}>
                                    Cancel
                                </Button>
                                <Button onClick={handleTransition} disabled={transitioning}>
                                    {transitioning ? 'Processing...' : transitionForm.deactivate_only ? 'End Loan' : 'Transition'}
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Preview Sync Modal */}
            {showPreviewSync && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <Card className="w-full max-w-2xl mx-4 max-h-[80vh] overflow-hidden flex flex-col">
                        <CardHeader>
                            <CardTitle>Preview Sync</CardTitle>
                            <CardDescription>
                                Compare API data with current database
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4 overflow-y-auto flex-1">
                            <div className="flex flex-wrap items-end gap-4">
                                <div className="min-w-[120px]">
                                    <Label>Season</Label>
                                    <select
                                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        value={previewSyncSeason}
                                        onChange={(e) => setPreviewSyncSeason(parseInt(e.target.value))}
                                    >
                                        <option value={2025}>2025-26</option>
                                        <option value={2024}>2024-25</option>
                                        <option value={2023}>2023-24</option>
                                    </select>
                                </div>
                                <div className="flex-1 min-w-[200px]">
                                    <Label>Team (required for seeding)</Label>
                                    <TeamSelect
                                        teams={teams}
                                        value={previewSyncTeamId}
                                        onChange={(val) => { setPreviewSyncTeamId(val); setPreviewSyncData(null) }}
                                        placeholder="Select parent club..."
                                    />
                                </div>
                                <div className="flex gap-2">
                                    <Button onClick={handlePreviewSync} disabled={previewSyncLoading}>
                                        {previewSyncLoading ? 'Loading...' : 'Check API'}
                                    </Button>
                                    <Button
                                        onClick={handleSeedTeam}
                                        disabled={seedingTeam || !previewSyncTeamId || !previewSyncData || previewSyncData.summary.new === 0}
                                        variant="default"
                                    >
                                        {seedingTeam ? 'Seeding...' : 'Seed Team'}
                                    </Button>
                                </div>
                            </div>

                            {previewSyncData && (
                                <div className="space-y-4">
                                    <div className="grid grid-cols-3 gap-4 text-center">
                                        <div className="p-3 bg-blue-50 rounded-lg">
                                            <div className="text-2xl font-bold text-blue-600">{previewSyncData.summary.new}</div>
                                            <div className="text-sm text-muted-foreground">New from API</div>
                                        </div>
                                        <div className="p-3 bg-green-50 rounded-lg">
                                            <div className="text-2xl font-bold text-green-600">{previewSyncData.summary.matches_manual}</div>
                                            <div className="text-sm text-muted-foreground">API Confirmed</div>
                                        </div>
                                        <div className="p-3 bg-gray-50 rounded-lg">
                                            <div className="text-2xl font-bold text-gray-600">{previewSyncData.summary.already_tracked}</div>
                                            <div className="text-sm text-muted-foreground">Already Tracked</div>
                                        </div>
                                    </div>

                                    {previewSyncData.new.length > 0 && (
                                        <div>
                                            <h4 className="font-medium mb-2">New Loans from API ({previewSyncData.new.length})</h4>
                                            <div className="space-y-2 max-h-40 overflow-y-auto">
                                                {previewSyncData.new.map((loan, i) => (
                                                    <div key={i} className="text-sm p-2 bg-blue-50 rounded">
                                                        <span className="font-bold">{loan.player_name}</span>
                                                        <span className="text-muted-foreground mx-2">•</span>
                                                        <span>{loan.primary_team_name}</span>
                                                        <span className="mx-2">→</span>
                                                        <span>{loan.loan_team_name}</span>
                                                        {loan.transfer_date && <span className="text-muted-foreground ml-2">({loan.transfer_date})</span>}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {previewSyncData.matches_manual.length > 0 && (
                                        <div>
                                            <h4 className="font-medium mb-2">Manual Loans Now Confirmed by API ({previewSyncData.matches_manual.length})</h4>
                                            <div className="space-y-2 max-h-40 overflow-y-auto">
                                                {previewSyncData.matches_manual.map((loan, i) => (
                                                    <div key={i} className="text-sm p-2 bg-green-50 rounded flex items-center justify-between">
                                                        <span>
                                                            <span className="font-medium">{loan.player_name}</span>
                                                            <span className="mx-2">at</span>
                                                            <span>{loan.loan_team_name}</span>
                                                        </span>
                                                        {loan.already_confirmed && (
                                                            <Badge variant="outline" className="text-green-600 text-xs">Already confirmed</Badge>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}

                            <div className="flex justify-end gap-2 pt-4 border-t">
                                <Button variant="outline" onClick={() => { setShowPreviewSync(false); setPreviewSyncData(null) }}>
                                    Close
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Info Card */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Search className="h-5 w-5" />
                        Managing Loans
                    </CardTitle>
                    <CardDescription>
                        How to work with loan records
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="rounded-lg border border-dashed bg-muted/40 p-6 text-sm text-muted-foreground space-y-2">
                        <p><strong>Viewing:</strong> Use filters to find specific loans by team, status, source, or player name.</p>
                        <p><strong>Editing:</strong> Click the <Pencil className="h-3 w-3 inline" /> icon to change the parent club or loan club for a player.</p>
                        <p><strong>Transitioning:</strong> Click the <ArrowRightLeft className="h-3 w-3 inline" /> icon to end a loan and move the player to a new club in one action.</p>
                        <p><strong>Bulk Actions:</strong> Use Select Mode to deactivate or transition multiple loans at once.</p>
                        <p><strong>Preview Sync:</strong> Compare what the API has vs your database before seeding.</p>
                        <p><strong>Manual Badge:</strong> <Badge variant="outline" className="text-purple-600 border-purple-300 text-xs">Manual</Badge> loans are protected from API seeding.</p>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
