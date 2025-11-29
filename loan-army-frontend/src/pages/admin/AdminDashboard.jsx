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

    // In a real app, you'd fetch these stats from the API
    useEffect(() => {
        // Placeholder - would call API here
        setStats({
            newsletters: { total: 0, published: 0, drafts: 0 },
            loans: { total: 0, active: 0 },
            players: { total: 0 },
        })
    }, [])
    
    // Goalkeeper saves resync handler
    const handleGkResync = async (dryRun = false) => {
        setGkResyncLoading(true)
        setGkResyncResult(null)
        try {
            const result = await APIService.request('/admin/resync-goalkeeper-saves', {
                method: 'POST',
                body: JSON.stringify({ dry_run: dryRun, limit: 100 }),
            })
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
                    Overview of your loan tracking system
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
