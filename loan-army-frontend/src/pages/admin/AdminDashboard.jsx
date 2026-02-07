import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Mail, Trophy, Users, Settings, TrendingUp, Calendar, RefreshCw, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { APIService } from '@/lib/api'

export function AdminDashboard() {
    const [stats, setStats] = useState({
        newsletters: { total: 0, published: 0, drafts: 0 },
        loans: { total: 0, active: 0 },
        players: { total: 0 },
    })
    
    // Goalkeeper saves resync state
    const [gkResyncLoading, setGkResyncLoading] = useState(false)
    const [gkResyncResult, setGkResyncResult] = useState(null)

    // Fix miscategorized loans state
    const [fixLoansLoading, setFixLoansLoading] = useState(false)
    const [fixLoansResult, setFixLoansResult] = useState(null)
    const [fixLoansJobId, setFixLoansJobId] = useState(null)
    const [fixLoansProgress, setFixLoansProgress] = useState(null)
    
    // Reconcile player IDs state
    const [reconcileLoading, setReconcileLoading] = useState(false)
    const [reconcileResult, setReconcileResult] = useState(null)
    const [reconcileJobId, setReconcileJobId] = useState(null)
    const [reconcileProgress, setReconcileProgress] = useState(null)
    
    // Sync limited stats state (for leagues without full player stats)
    const [limitedStatsLoading, setLimitedStatsLoading] = useState(false)
    const [limitedStatsResult, setLimitedStatsResult] = useState(null)

    // Fetch dashboard stats
    useEffect(() => {
        const loadStats = async () => {
            try {
                const data = await APIService.request('/admin/dashboard-stats', {}, { admin: true })
                setStats(data)
            } catch (error) {
                console.error('Failed to load dashboard stats:', error)
                // Keep defaults on error
            }
        }
        loadStats()
    }, [])
    
    // Goalkeeper saves resync handler
    const handleGkResync = async (dryRun = false) => {
        setGkResyncLoading(true)
        setGkResyncResult(null)
        try {
            const result = await APIService.request('/admin/resync-goalkeeper-saves', {
                method: 'POST',
                body: JSON.stringify({ dry_run: dryRun, limit: 100 }),
            }, { admin: true })
            setGkResyncResult({
                success: true,
                dryRun,
                ...result
            })
        } catch (error) {
            setGkResyncResult({
                success: false,
                error: error.message || 'Failed to resync'
            })
        } finally {
            setGkResyncLoading(false)
        }
    }
    
    // Fix miscategorized loans handler
    const handleFixLoans = async (dryRun = false, processAll = false) => {
        setFixLoansLoading(true)
        setFixLoansResult(null)
        setFixLoansJobId(null)
        setFixLoansProgress(null)
        
        try {
            const result = await APIService.request('/admin/loans/fix-miscategorized', {
                method: 'POST',
                body: JSON.stringify({ 
                    dry_run: dryRun,
                    limit: processAll ? 0 : 50,
                    background: processAll
                }),
            }, { admin: true })
            
            if (result.job_id) {
                // Background job started - poll for status
                setFixLoansJobId(result.job_id)
                pollFixLoansJobStatus(result.job_id, dryRun)
            } else {
                // Synchronous result
                setFixLoansResult({
                    success: true,
                    dryRun,
                    ...result
                })
                setFixLoansLoading(false)
            }
        } catch (error) {
            setFixLoansResult({
                success: false,
                error: error.message || 'Failed to fix loans'
            })
            setFixLoansLoading(false)
        }
    }
    
    const pollFixLoansJobStatus = async (jobId, dryRun) => {
        try {
            const status = await APIService.request(`/admin/jobs/${jobId}`, {}, { admin: true })
            setFixLoansProgress(status)
            
            if (status.status === 'completed') {
                setFixLoansResult({
                    success: true,
                    dryRun,
                    ...status.results
                })
                setFixLoansLoading(false)
                setFixLoansJobId(null)
            } else if (status.status === 'failed') {
                setFixLoansResult({
                    success: false,
                    error: status.error || 'Job failed'
                })
                setFixLoansLoading(false)
                setFixLoansJobId(null)
            } else {
                // Still running - poll again in 3 seconds
                setTimeout(() => pollFixLoansJobStatus(jobId, dryRun), 3000)
            }
        } catch (error) {
            console.error('Failed to poll job status:', error)
            setTimeout(() => pollFixLoansJobStatus(jobId, dryRun), 5000)
        }
    }
    
    // Reconcile player IDs handler
    const handleReconcileIds = async (dryRun = false, processAll = false) => {
        setReconcileLoading(true)
        setReconcileResult(null)
        setReconcileJobId(null)
        setReconcileProgress(null)
        
        try {
            const result = await APIService.request('/admin/loans/reconcile-ids', {
                method: 'POST',
                body: JSON.stringify({ 
                    dry_run: dryRun, 
                    limit: processAll ? 0 : 50,
                    background: processAll 
                }),
            }, { admin: true })
            
            if (result.job_id) {
                // Background job started - poll for status
                setReconcileJobId(result.job_id)
                pollJobStatus(result.job_id, dryRun)
            } else {
                // Synchronous result
                setReconcileResult({
                    success: true,
                    dryRun,
                    ...result
                })
                setReconcileLoading(false)
            }
        } catch (error) {
            setReconcileResult({
                success: false,
                error: error.message || 'Failed to reconcile IDs'
            })
            setReconcileLoading(false)
        }
    }
    
    const pollJobStatus = async (jobId, dryRun) => {
        try {
            const status = await APIService.request(`/admin/jobs/${jobId}`, {}, { admin: true })
            setReconcileProgress(status)
            
            if (status.status === 'completed') {
                setReconcileResult({
                    success: true,
                    dryRun,
                    ...status.results
                })
                setReconcileLoading(false)
                setReconcileJobId(null)
            } else if (status.status === 'failed') {
                setReconcileResult({
                    success: false,
                    error: status.error || 'Job failed'
                })
                setReconcileLoading(false)
                setReconcileJobId(null)
            } else {
                // Still running - poll again in 3 seconds
                setTimeout(() => pollJobStatus(jobId, dryRun), 3000)
            }
        } catch (error) {
            console.error('Failed to poll job status:', error)
            // Keep polling on error
            setTimeout(() => pollJobStatus(jobId, dryRun), 5000)
        }
    }
    
    // Sync limited stats handler (for leagues like National League without full player stats)
    const handleSyncLimitedStats = async (dryRun = false, force = false) => {
        console.log('🔄 Starting sync limited stats...', { dryRun, force })
        setLimitedStatsLoading(true)
        setLimitedStatsResult(null)
        try {
            const result = await APIService.request('/admin/sync-limited-stats', {
                method: 'POST',
                body: JSON.stringify({ dry_run: dryRun, force }),
            }, { admin: true })
            console.log('✅ Sync limited stats result:', result)
            setLimitedStatsResult({
                success: true,
                dryRun,
                ...result
            })
        } catch (error) {
            console.error('❌ Sync limited stats error:', error)
            setLimitedStatsResult({
                success: false,
                error: error.message || 'Failed to sync limited stats'
            })
        } finally {
            setLimitedStatsLoading(false)
        }
    }

    const quickActions = [
        {
            title: 'Generate Newsletter',
            description: 'Create newsletters for selected teams',
            icon: Mail,
            href: '/admin/newsletters',
            color: 'blue'
        },
        {
            title: 'Manage Loans',
            description: 'View and manage active loan records',
            icon: Trophy,
            href: '/admin/loans',
            color: 'green'
        },
        {
            title: 'Add Player',
            description: 'Manually add a new loan player',
            icon: Users,
            href: '/admin/players',
            color: 'purple'
        },
        {
            title: 'Settings',
            description: 'Configure API keys and system settings',
            icon: Settings,
            href: '/admin/settings',
            color: 'gray'
        },
        {
            title: 'Manage Users',
            description: 'View all users and their subscriptions',
            icon: Users,
            href: '/admin/users',
            color: 'indigo'
        },
        {
            title: 'Manage Teams',
            description: 'Track/untrack teams and delete team data',
            icon: Trophy,
            href: '/admin/teams',
            color: 'orange'
        },
    ]

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
                <p className="text-muted-foreground mt-1">
                    Overview of your academy tracking system
                </p>
            </div>

            {/* Stats Grid */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Newsletters</CardTitle>
                        <Mail className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.newsletters.total}</div>
                        <p className="text-xs text-muted-foreground">
                            {stats.newsletters.published} published, {stats.newsletters.drafts} drafts
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Active Loans</CardTitle>
                        <Trophy className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.loans.active}</div>
                        <p className="text-xs text-muted-foreground">
                            {stats.loans.total} total loan records
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Players</CardTitle>
                        <Users className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.players.total}</div>
                        <p className="text-xs text-muted-foreground">
                            Tracked across all teams
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* Quick Actions */}
            <div>
                <h3 className="text-xl font-semibold mb-4">Quick Actions</h3>
                <div className="grid gap-4 md:grid-cols-2">
                    {quickActions.map((action) => (
                        <Link key={action.href} to={action.href}>
                            <Card className="hover:bg-accent hover:shadow-md transition-all cursor-pointer h-full">
                                <CardHeader>
                                    <div className="flex items-center gap-3">
                                        <div className={`p-2 rounded-lg bg-${action.color}-100`}>
                                            <action.icon className={`h-5 w-5 text-${action.color}-600`} />
                                        </div>
                                        <div>
                                            <CardTitle className="text-base">{action.title}</CardTitle>
                                            <CardDescription>{action.description}</CardDescription>
                                        </div>
                                    </div>
                                </CardHeader>
                            </Card>
                        </Link>
                    ))}
                </div>
            </div>

            {/* Data Maintenance Section */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <RefreshCw className="h-5 w-5" />
                        Data Maintenance
                    </CardTitle>
                    <CardDescription>Fix and resync player statistics</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="border rounded-lg p-4 bg-muted/30">
                        <h4 className="font-semibold text-sm mb-2">Resync Goalkeeper Saves</h4>
                        <p className="text-sm text-muted-foreground mb-3">
                            Re-fetch saves data from API-Football for goalkeeper fixtures that are missing this stat.
                        </p>
                        <div className="flex gap-2 flex-wrap">
                            <Button 
                                variant="outline" 
                                size="sm"
                                onClick={() => handleGkResync(true)}
                                disabled={gkResyncLoading}
                            >
                                {gkResyncLoading ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : null}
                                Preview (Dry Run)
                            </Button>
                            <Button 
                                variant="default" 
                                size="sm"
                                onClick={() => handleGkResync(false)}
                                disabled={gkResyncLoading}
                            >
                                {gkResyncLoading ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                    <RefreshCw className="h-4 w-4 mr-2" />
                                )}
                                Run Resync
                            </Button>
                        </div>
                        
                        {/* Result display */}
                        {gkResyncResult && (
                            <div className={`mt-4 p-3 rounded-md text-sm ${
                                gkResyncResult.success 
                                    ? 'bg-green-50 border border-green-200' 
                                    : 'bg-red-50 border border-red-200'
                            }`}>
                                {gkResyncResult.success ? (
                                    <div className="space-y-1">
                                        <div className="flex items-center gap-2 font-medium">
                                            <CheckCircle className="h-4 w-4 text-green-600" />
                                            {gkResyncResult.dryRun ? 'Dry Run Complete' : 'Resync Complete'}
                                        </div>
                                        <div className="text-muted-foreground">
                                            Found: {gkResyncResult.found} fixtures • 
                                            {gkResyncResult.dryRun ? ' Would update' : ' Updated'}: {gkResyncResult.updated} • 
                                            Skipped: {gkResyncResult.skipped} • 
                                            Errors: {gkResyncResult.errors}
                                        </div>
                                        {gkResyncResult.found > 0 && gkResyncResult.dryRun && (
                                            <div className="text-blue-600 mt-1">
                                                Click "Run Resync" to apply these changes.
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center gap-2">
                                        <AlertCircle className="h-4 w-4 text-red-600" />
                                        <span className="text-red-700">{gkResyncResult.error}</span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                    
                    {/* Verify & Fix Loans */}
                    <div className="border rounded-lg p-4 bg-muted/30">
                        <h4 className="font-semibold text-sm mb-2">Verify & Fix Loan Records</h4>
                        <p className="text-sm text-muted-foreground mb-3">
                            Re-verify loan records against API-Football transfer data. This catches cases where 
                            loan returns were misidentified as new loans (causing parent/loan teams to be swapped).
                        </p>
                        <div className="flex gap-2 flex-wrap">
                            <Button 
                                variant="outline" 
                                size="sm"
                                onClick={() => handleFixLoans(true)}
                                disabled={fixLoansLoading}
                            >
                                {fixLoansLoading ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : null}
                                Preview (Dry Run)
                            </Button>
                            <Button 
                                variant="default" 
                                size="sm"
                                onClick={() => handleFixLoans(false)}
                                disabled={fixLoansLoading}
                            >
                                {fixLoansLoading && !fixLoansJobId ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                    <RefreshCw className="h-4 w-4 mr-2" />
                                )}
                                Verify & Fix (50)
                            </Button>
                            <Button 
                                variant="secondary" 
                                size="sm"
                                onClick={() => handleFixLoans(false, true)}
                                disabled={fixLoansLoading}
                            >
                                {fixLoansLoading && fixLoansJobId ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : null}
                                Process All
                            </Button>
                        </div>
                        
                        {/* Background job progress */}
                        {fixLoansJobId && fixLoansProgress && (
                            <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded text-sm">
                                <div className="flex items-center gap-2">
                                    <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                                    <span className="font-medium">Processing in background...</span>
                                </div>
                                <div className="text-xs text-blue-700 mt-1">
                                    Progress: {fixLoansProgress.progress || 0} / {fixLoansProgress.total || '?'}
                                    {fixLoansProgress.current_player && (
                                        <span className="ml-2">• Current: {fixLoansProgress.current_player}</span>
                                    )}
                                </div>
                            </div>
                        )}
                        
                        {/* Result display */}
                        {fixLoansResult && (
                            <div className={`mt-4 p-3 rounded-md text-sm ${
                                fixLoansResult.success 
                                    ? 'bg-green-50 border border-green-200' 
                                    : 'bg-red-50 border border-red-200'
                            }`}>
                                {fixLoansResult.success ? (
                                    <div className="space-y-1">
                                        <div className="flex items-center gap-2 font-medium">
                                            <CheckCircle className="h-4 w-4 text-green-600" />
                                            {fixLoansResult.dryRun ? 'Verification Preview' : 'Verification Complete'}
                                        </div>
                                        <div className="text-muted-foreground">
                                            Checked: {fixLoansResult.checked} • 
                                            Correct: {fixLoansResult.verified_correct} • 
                                            {fixLoansResult.dryRun ? 'Would fix' : 'Fixed'}: {fixLoansResult.fixed} • 
                                            No API match: {fixLoansResult.no_loan_found} • 
                                            Errors: {fixLoansResult.api_errors}
                                        </div>
                                        {fixLoansResult.fixed > 0 && fixLoansResult.dryRun && (
                                            <div className="text-blue-600 mt-1">
                                                Click "Verify & Fix" to apply these corrections.
                                            </div>
                                        )}
                                        {fixLoansResult.details && fixLoansResult.details.length > 0 && (
                                            <details className="mt-2">
                                                <summary className="cursor-pointer text-blue-600 hover:underline">
                                                    Show details ({fixLoansResult.details.length} records)
                                                </summary>
                                                <div className="mt-2 max-h-64 overflow-y-auto text-xs space-y-1">
                                                    {fixLoansResult.details.map((d, i) => (
                                                        <div key={i} className={`p-2 rounded border ${
                                                            d.status === 'verified_correct' ? 'bg-green-50 border-green-200' :
                                                            d.status === 'would_fix' || d.status === 'fixed' ? 'bg-yellow-50 border-yellow-200' :
                                                            'bg-gray-50 border-gray-200'
                                                        }`}>
                                                            <strong>{d.player_name}</strong>
                                                            {d.status === 'verified_correct' && (
                                                                <span className="text-green-600 ml-1">
                                                                    ✓ Correct: {d.parent} → {d.loan}
                                                                </span>
                                                            )}
                                                            {(d.status === 'would_fix' || d.status === 'fixed') && (
                                                                <span className="text-yellow-700 ml-1">
                                                                    ⚠️ {d.old_parent} → {d.old_loan} 
                                                                    <span className="text-green-600"> → Fixed: {d.new_parent} → {d.new_loan}</span>
                                                                </span>
                                                            )}
                                                            {d.status === 'no_matching_loan_in_api' && (
                                                                <span className="text-gray-500 ml-1">
                                                                    ⚪ No matching loan found in API
                                                                </span>
                                                            )}
                                                            {d.status === 'api_error' && (
                                                                <span className="text-red-500 ml-1">
                                                                    ❌ API error
                                                                </span>
                                                            )}
                                                        </div>
                                                    ))}
                                                </div>
                                            </details>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center gap-2">
                                        <AlertCircle className="h-4 w-4 text-red-600" />
                                        <span className="text-red-700">{fixLoansResult.error}</span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                    
                    {/* Reconcile Player IDs & Sync Stats */}
                    <div className="border rounded-lg p-4 bg-muted/30">
                        <h4 className="font-semibold text-sm mb-2">Reconcile IDs & Sync Stats</h4>
                        <p className="text-sm text-muted-foreground mb-3">
                            For players with 0 appearances: checks recent + full season fixtures, then verifies via squad API.
                            Fixes ID mismatches, syncs stats, or confirms player status.
                        </p>
                        <div className="flex gap-2 flex-wrap">
                            <Button 
                                variant="outline" 
                                size="sm"
                                onClick={() => handleReconcileIds(true)}
                                disabled={reconcileLoading}
                            >
                                {reconcileLoading ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : null}
                                Preview
                            </Button>
                            <Button 
                                variant="default" 
                                size="sm"
                                onClick={() => handleReconcileIds(false)}
                                disabled={reconcileLoading}
                            >
                                {reconcileLoading && !reconcileJobId ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                    <RefreshCw className="h-4 w-4 mr-2" />
                                )}
                                Fix & Sync (50)
                            </Button>
                            <Button 
                                variant="secondary" 
                                size="sm"
                                onClick={() => handleReconcileIds(false, true)}
                                disabled={reconcileLoading}
                            >
                                {reconcileLoading && reconcileJobId ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : null}
                                Process All
                            </Button>
                        </div>
                        
                        {/* Background job progress */}
                        {reconcileJobId && reconcileProgress && (
                            <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded text-sm">
                                <div className="flex items-center gap-2">
                                    <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                                    <span className="font-medium">Processing in background...</span>
                                </div>
                                <div className="text-xs text-blue-700 mt-1">
                                    Progress: {reconcileProgress.progress || 0} / {reconcileProgress.total || '?'}
                                    {reconcileProgress.current_player && (
                                        <span className="ml-2">• Current: {reconcileProgress.current_player}</span>
                                    )}
                                </div>
                            </div>
                        )}
                        
                        {/* Result display */}
                        {reconcileResult && (
                            <div className={`mt-4 p-3 rounded-md text-sm ${
                                reconcileResult.success 
                                    ? 'bg-green-50 border border-green-200' 
                                    : 'bg-red-50 border border-red-200'
                            }`}>
                                {reconcileResult.success ? (
                                    <div className="space-y-1">
                                        <div className="flex items-center gap-2 font-medium">
                                            <CheckCircle className="h-4 w-4 text-green-600" />
                                            {reconcileResult.dryRun ? 'Preview Complete' : 'Sync Complete'}
                                        </div>
                                        <div className="text-muted-foreground text-xs space-y-0.5">
                                            <div>Checked: {reconcileResult.checked} players with 0 stats</div>
                                            <div className="flex flex-wrap gap-x-3">
                                                <span>🔄 IDs via fixtures: {reconcileResult.id_reconciled || 0}</span>
                                                <span>🔄 IDs via squad: {reconcileResult.id_reconciled_via_squad || 0}</span>
                                                <span>✓ Stats synced: {reconcileResult.stats_synced || 0}</span>
                                            </div>
                                            <div className="flex flex-wrap gap-x-3">
                                                <span>✓ Verified (no appearances): {reconcileResult.verified_no_appearances || 0}</span>
                                                <span>🔀 Loan moved: {reconcileResult.loan_destination_changed || 0}</span>
                                            </div>
                                            <div className="flex flex-wrap gap-x-3">
                                                <span>🚪 Left club: {reconcileResult.player_left_club || 0}</span>
                                                <span>👥 Duplicates: {reconcileResult.duplicate_detected || 0}</span>
                                                <span>⚠ Not in squad: {reconcileResult.not_in_squad || 0}</span>
                                            </div>
                                        </div>
                                        {((reconcileResult.id_reconciled || 0) + (reconcileResult.id_reconciled_via_squad || 0) + (reconcileResult.stats_synced || 0) + (reconcileResult.loan_destination_changed || 0) + (reconcileResult.player_left_club || 0) + (reconcileResult.duplicate_detected || 0) > 0) && reconcileResult.dryRun && (
                                            <div className="text-blue-600 mt-1">
                                                Click "Fix & Sync" to apply these changes.
                                            </div>
                                        )}
                                        {reconcileResult.details && reconcileResult.details.length > 0 && (
                                            <details className="mt-2">
                                                <summary className="cursor-pointer text-blue-600 hover:underline">
                                                    Show details ({reconcileResult.details.length} records)
                                                </summary>
                                                <div className="mt-2 max-h-64 overflow-y-auto text-xs space-y-1">
                                                    {reconcileResult.details.map((d, i) => (
                                                        <div key={i} className={`p-2 rounded border ${
                                                            d.action === 'id_reconcile' ? 'bg-purple-50 border-purple-200' :
                                                            d.action === 'id_reconcile_via_squad' ? 'bg-purple-50 border-purple-200' :
                                                            d.action === 'stats_sync' ? 'bg-green-50 border-green-200' :
                                                            d.action === 'verified_no_appearances' ? 'bg-blue-50 border-blue-200' :
                                                            d.action === 'loan_destination_changed' ? 'bg-cyan-50 border-cyan-200' :
                                                            d.action === 'player_left_club' ? 'bg-red-50 border-red-200' :
                                                            d.action === 'duplicate_detected' ? 'bg-yellow-50 border-yellow-200' :
                                                            d.action === 'not_in_squad' ? 'bg-orange-50 border-orange-200' :
                                                            'bg-gray-50 border-gray-200'
                                                        }`}>
                                                            <strong>{d.player_name}</strong> ({d.loan_team || d.old_loan_team})
                                                            {d.action === 'id_reconcile' && (
                                                                <div className="text-purple-600 mt-1">
                                                                    🔄 ID fixed (via fixtures): {d.old_player_id} → {d.new_player_id}
                                                                </div>
                                                            )}
                                                            {d.action === 'id_reconcile_via_squad' && (
                                                                <div className="text-purple-600 mt-1">
                                                                    🔄 ID fixed (via squad): {d.old_player_id} → {d.new_player_id}
                                                                </div>
                                                            )}
                                                            {d.action === 'stats_sync' && (
                                                                <div className="text-green-600 mt-1">
                                                                    ✓ {reconcileResult.dryRun ? 'Would sync' : 'Synced'} {d.fixtures_synced || d.fixtures_found} fixture(s)
                                                                </div>
                                                            )}
                                                            {d.action === 'verified_no_appearances' && (
                                                                <div className="text-blue-600 mt-1">
                                                                    ✓ In squad (#{d.squad_number || '?'} {d.squad_position || ''}) - 0 appearances
                                                                </div>
                                                            )}
                                                            {d.action === 'loan_destination_changed' && (
                                                                <div className="text-cyan-600 mt-1">
                                                                    🔀 Consecutive loan: {d.old_loan_team} → <strong>{d.new_loan_team}</strong>
                                                                    <span className="text-gray-500 ml-1">({d.transfer_date})</span>
                                                                </div>
                                                            )}
                                                            {d.action === 'player_left_club' && (
                                                                <div className="text-red-600 mt-1">
                                                                    🚪 Left club: {d.transfer_type} on {d.transfer_date}
                                                                    <span className="text-gray-500 ml-1">→ {d.destination}</span>
                                                                    <div className="text-xs">{reconcileResult.dryRun ? 'Would deactivate' : 'Deactivated'} loan record</div>
                                                                </div>
                                                            )}
                                                            {d.action === 'duplicate_detected' && (
                                                                <div className="text-yellow-700 mt-1">
                                                                    👥 Duplicate: newer record exists as <strong>{d.duplicate_name}</strong> at {d.duplicate_team}
                                                                    <div className="text-xs">{reconcileResult.dryRun ? 'Would deactivate' : 'Deactivated'} this old record</div>
                                                                </div>
                                                            )}
                                                            {d.action === 'not_in_squad' && (
                                                                <div className="text-orange-600 mt-1">
                                                                    ⚠ Not found in squad - may have left club
                                                                </div>
                                                            )}
                                                            {d.status === 'error' && (
                                                                <span className="text-red-500 ml-1">
                                                                    ❌ {d.error}
                                                                </span>
                                                            )}
                                                        </div>
                                                    ))}
                                                </div>
                                            </details>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center gap-2">
                                        <AlertCircle className="h-4 w-4 text-red-600" />
                                        <span className="text-red-700">{reconcileResult.error}</span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                    
                    {/* Sync Limited Stats */}
                    <div className="border rounded-lg p-4 bg-muted/30">
                        <h4 className="font-semibold text-sm mb-2">Sync Limited Stats (Lower Leagues)</h4>
                        <p className="text-sm text-muted-foreground mb-3">
                            For players in leagues without full stats coverage (e.g., National League), 
                            fetch appearances, goals, and assists from lineup and events data.
                        </p>
                        <div className="flex gap-2 flex-wrap">
                            <Button 
                                variant="outline" 
                                size="sm"
                                onClick={() => handleSyncLimitedStats(true)}
                                disabled={limitedStatsLoading}
                            >
                                {limitedStatsLoading ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : null}
                                Preview (Dry Run)
                            </Button>
                            <Button 
                                variant="default" 
                                size="sm"
                                onClick={() => handleSyncLimitedStats(false)}
                                disabled={limitedStatsLoading}
                            >
                                {limitedStatsLoading ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                    <RefreshCw className="h-4 w-4 mr-2" />
                                )}
                                Sync Stats
                            </Button>
                            <Button 
                                variant="secondary" 
                                size="sm"
                                onClick={() => handleSyncLimitedStats(false, true)}
                                disabled={limitedStatsLoading}
                            >
                                Force Re-sync All
                            </Button>
                        </div>
                        
                        {/* Result display */}
                        {limitedStatsResult && (
                            <div className={`mt-4 p-3 rounded-md text-sm ${
                                limitedStatsResult.success 
                                    ? 'bg-green-50 border border-green-200' 
                                    : 'bg-red-50 border border-red-200'
                            }`}>
                                {limitedStatsResult.success ? (
                                    <div className="space-y-1">
                                        <div className="flex items-center gap-2 font-medium">
                                            <CheckCircle className="h-4 w-4 text-green-600" />
                                            {limitedStatsResult.dryRun ? 'Preview Complete' : 'Sync Complete'}
                                        </div>
                                        <div className="text-muted-foreground">
                                            Found: {limitedStatsResult.found} limited coverage players • 
                                            {limitedStatsResult.dryRun ? ' Would update' : ' Updated'}: {limitedStatsResult.updated} • 
                                            Skipped: {limitedStatsResult.skipped} • 
                                            Errors: {limitedStatsResult.errors}
                                        </div>
                                        {limitedStatsResult.updated > 0 && limitedStatsResult.dryRun && (
                                            <div className="text-blue-600 mt-1">
                                                Click "Sync Stats" to apply these changes.
                                            </div>
                                        )}
                                        {limitedStatsResult.details && limitedStatsResult.details.length > 0 && (
                                            <details className="mt-2">
                                                <summary className="cursor-pointer text-blue-600 hover:underline">
                                                    Show details ({limitedStatsResult.details.length} players)
                                                </summary>
                                                <div className="mt-2 max-h-64 overflow-y-auto text-xs space-y-1">
                                                    {limitedStatsResult.details.map((d, i) => (
                                                        <div key={i} className={`p-2 rounded border ${
                                                            d.status === 'updated' || d.status === 'would_update' ? 'bg-green-50 border-green-200' :
                                                            d.status === 'skipped_has_stats' ? 'bg-gray-50 border-gray-200' :
                                                            d.status?.startsWith('error') ? 'bg-red-50 border-red-200' :
                                                            'bg-gray-50 border-gray-200'
                                                        }`}>
                                                            <strong>{d.player_name}</strong>
                                                            {(d.status === 'updated' || d.status === 'would_update') && d.stats && (
                                                                <span className="text-green-600 ml-2">
                                                                    {d.stats.appearances} apps, {d.stats.goals}G, {d.stats.assists}A
                                                                </span>
                                                            )}
                                                            {d.status === 'would_update' && d.new_stats && (
                                                                <span className="text-green-600 ml-2">
                                                                    {d.new_stats.appearances} apps, {d.new_stats.goals}G, {d.new_stats.assists}A
                                                                </span>
                                                            )}
                                                            {d.status === 'skipped_has_stats' && (
                                                                <span className="text-gray-500 ml-2">
                                                                    Already has {d.appearances} appearances
                                                                </span>
                                                            )}
                                                            {d.status?.startsWith('error') && (
                                                                <span className="text-red-500 ml-2">
                                                                    {d.status}
                                                                </span>
                                                            )}
                                                        </div>
                                                    ))}
                                                </div>
                                            </details>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center gap-2">
                                        <AlertCircle className="h-4 w-4 text-red-600" />
                                        <span className="text-red-700">{limitedStatsResult.error}</span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* Recent Activity / Help Section */}
            <Card>
                <CardHeader>
                    <CardTitle>Getting Started</CardTitle>
                    <CardDescription>Common admin tasks and workflows</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                    <div className="border-l-4 border-blue-500 pl-4 py-2">
                        <h4 className="font-semibold text-sm">1. Configure Settings</h4>
                        <p className="text-sm text-muted-foreground">
                            Add your admin API key and configure newsletter settings in the Settings page
                        </p>
                    </div>
                    <div className="border-l-4 border-green-500 pl-4 py-2">
                        <h4 className="font-semibold text-sm">2. Seed Loan Data</h4>
                        <p className="text-sm text-muted-foreground">
                            Use the Newsletters page to seed Top-5 leagues or specific teams with loan data
                        </p>
                    </div>
                    <div className="border-l-4 border-purple-500 pl-4 py-2">
                        <h4 className="font-semibold text-sm">3. Generate Newsletters</h4>
                        <p className="text-sm text-muted-foreground">
                            Create newsletters for selected teams or all teams with recent loan activity
                        </p>
                    </div>
                    <div className="border-l-4 border-orange-500 pl-4 py-2">
                        <h4 className="font-semibold text-sm">4. Add Missing Players</h4>
                        <p className="text-sm text-muted-foreground">
                            Manually add players who didn't appear in the seeding process via the Players page
                        </p>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
