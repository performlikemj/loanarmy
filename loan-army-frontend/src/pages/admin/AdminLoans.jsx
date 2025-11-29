import { useState, useEffect } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Trophy, Search, AlertCircle, CheckCircle2, Filter, Pencil, X, Save, Power } from 'lucide-react'
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
        is_active: true
    })
    const [saving, setSaving] = useState(false)

    // Filters
    const [filters, setFilters] = useState({
        active_only: 'true',
        primary_team_db_id: '',
        player_name: ''
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

    // Load on mount and when filters change
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
            player_name: ''
        })
        // Will reload via effect
    }

    // Start editing a loan
    const startEdit = (loan) => {
        setEditingLoanId(loan.id)
        setEditForm({
            primary_team_db_id: loan.primary_team_id || '',
            loan_team_db_id: loan.loan_team_id || '',
            is_active: loan.is_active
        })
        setMessage(null)
    }

    // Cancel editing
    const cancelEdit = () => {
        setEditingLoanId(null)
        setEditForm({
            primary_team_db_id: '',
            loan_team_db_id: '',
            is_active: true
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
                is_active: editForm.is_active
            }
            await APIService.adminLoanUpdate(editingLoanId, payload)
            setMessage({ type: 'success', text: 'Loan updated successfully' })
            cancelEdit()
            loadLoans()
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
            setMessage({ type: 'success', text: 'Loan deactivated' })
            loadLoans()
        } catch (error) {
            console.error('Failed to deactivate loan', error)
            setMessage({ type: 'error', text: error?.body?.error || 'Failed to deactivate loan' })
        }
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Loans</h2>
                    <p className="text-muted-foreground mt-1">View and manage loan records</p>
                </div>
                <Button onClick={loadLoans} disabled={loading}>
                    <Trophy className="h-4 w-4 mr-2" />
                    Refresh
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
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
                    <CardTitle>Loan Records ({loans.length})</CardTitle>
                    <CardDescription>
                        {filters.active_only === 'true' ? 'Showing active loans only' : 'Showing all loan records'}
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="text-center py-8 text-muted-foreground">
                            Loading loans...
                        </div>
                    ) : loans.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <Trophy className="h-12 w-12 mx-auto mb-3 opacity-50" />
                            <p>No loans found</p>
                            <p className="text-sm mt-1">Try adjusting your filters or seed loan data from the Newsletters page</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {loans.map((loan) => (
                                <div
                                    key={loan.id}
                                    className={`border rounded-lg p-4 transition-colors ${editingLoanId === loan.id ? 'border-blue-300 bg-blue-50/50' : 'hover:bg-accent/50'}`}
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
                                            <div className="space-y-1 flex-1">
                                                <div className="flex items-center gap-2">
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
                                                    <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={() => deactivateLoan(loan.id)}
                                                        title="Deactivate loan"
                                                        className="text-orange-600 hover:text-orange-700 hover:bg-orange-50"
                                                    >
                                                        <Power className="h-4 w-4" />
                                                    </Button>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

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
                        <p><strong>Viewing:</strong> Use filters to find specific loans by team, status, or player name.</p>
                        <p><strong>Editing:</strong> Click the <Pencil className="h-3 w-3 inline" /> icon to change the parent club or loan club for a player.</p>
                        <p><strong>Deactivating:</strong> Click the <Power className="h-3 w-3 inline" /> icon to mark a loan as no longer active (e.g., loan ended, player returned).</p>
                        <p><strong>Adding:</strong> New loans are created automatically when you seed data or add players via the Players page.</p>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
