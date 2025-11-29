import React, { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
    Drawer,
    DrawerContent,
    DrawerHeader,
    DrawerTitle,
    DrawerDescription,
} from '@/components/ui/drawer'
import {
    LineChart,
    Line,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    ReferenceLine,
} from 'recharts'
import { Loader2, ArrowLeft, User, TrendingUp, Calendar, Target, PenTool, ChevronRight, Users } from 'lucide-react'
import { APIService } from '@/lib/api'
import { format } from 'date-fns'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

const METRIC_CONFIG = {
    'Attacker': {
        default: ['goals', 'shots_total', 'shots_on'],
        options: [
            { key: 'goals', label: 'Goals', color: '#2563eb' },
            { key: 'assists', label: 'Assists', color: '#16a34a' },
            { key: 'shots_total', label: 'Shots', color: '#9333ea' },
            { key: 'shots_on', label: 'Shots on Target', color: '#d946ef' },
            { key: 'dribbles_success', label: 'Dribbles', color: '#f59e0b' },
            { key: 'passes_key', label: 'Key Passes', color: '#06b6d4' },
        ]
    },
    'Midfielder': {
        default: ['passes_total', 'passes_key', 'tackles_total'],
        options: [
            { key: 'goals', label: 'Goals', color: '#2563eb' },
            { key: 'assists', label: 'Assists', color: '#16a34a' },
            { key: 'passes_total', label: 'Passes', color: '#9333ea' },
            { key: 'passes_key', label: 'Key Passes', color: '#d946ef' },
            { key: 'tackles_total', label: 'Tackles', color: '#f59e0b' },
            { key: 'duels_won', label: 'Duels Won', color: '#06b6d4' },
            { key: 'interceptions', label: 'Interceptions', color: '#ea580c' },
        ]
    },
    'Defender': {
        default: ['tackles_total', 'duels_won', 'interceptions'],
        options: [
            { key: 'tackles_total', label: 'Tackles', color: '#2563eb' },
            { key: 'duels_won', label: 'Duels Won', color: '#16a34a' },
            { key: 'interceptions', label: 'Interceptions', color: '#9333ea' },
            { key: 'blocks', label: 'Blocks', color: '#d946ef' },
            { key: 'clearances', label: 'Clearances', color: '#f59e0b' },
            { key: 'passes_total', label: 'Passes', color: '#06b6d4' },
        ]
    },
    'Goalkeeper': {
        default: ['saves', 'passes_total'],
        options: [
            { key: 'saves', label: 'Saves', color: '#2563eb' },
            { key: 'passes_total', label: 'Passes', color: '#16a34a' },
            { key: 'rating', label: 'Rating', color: '#9333ea' },
        ]
    }
}

const DEFAULT_POSITION = 'Midfielder'

export function PlayerPage() {
    const { playerId } = useParams()
    const navigate = useNavigate()
    const [profile, setProfile] = useState(null)
    const [stats, setStats] = useState([])
    const [seasonStats, setSeasonStats] = useState(null)
    const [commentaries, setCommentaries] = useState({ commentaries: [], authors: [], total_count: 0 })
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [position, setPosition] = useState(DEFAULT_POSITION)
    const [selectedMetrics, setSelectedMetrics] = useState([])
    
    // Team players drawer state
    const [drawerOpen, setDrawerOpen] = useState(false)
    const [teamPlayers, setTeamPlayers] = useState([])
    const [loadingTeamPlayers, setLoadingTeamPlayers] = useState(false)

    // Smart back navigation - goes to previous page, or home if no history
    const handleBack = () => {
        // Check if we have navigation history within the app
        if (window.history.length > 1) {
            navigate(-1)
        } else {
            // Fallback to home page if no history (direct link/bookmark)
            navigate('/')
        }
    }

    useEffect(() => {
        if (playerId) {
            loadPlayerData()
        }
    }, [playerId])

    const loadPlayerData = async () => {
        setLoading(true)
        setError(null)
        try {
            const [profileData, statsData, seasonData, commentariesData] = await Promise.all([
                APIService.getPublicPlayerProfile(playerId).catch(() => null),
                APIService.getPublicPlayerStats(playerId),
                APIService.getPublicPlayerSeasonStats(playerId).catch(() => null),
                APIService.getPlayerCommentaries(playerId).catch(() => ({ commentaries: [], authors: [], total_count: 0 }))
            ])
            
            setProfile(profileData)
            setStats(statsData || [])
            setSeasonStats(seasonData)
            setCommentaries(commentariesData || { commentaries: [], authors: [], total_count: 0 })

            // Infer position from stats
            if (statsData && statsData.length > 0) {
                const positions = statsData.map(s => s.position).filter(Boolean)
                if (positions.length > 0) {
                    const counts = positions.reduce((acc, p) => {
                        acc[p] = (acc[p] || 0) + 1
                        return acc
                    }, {})
                    const likelyPos = Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b)

                    let mappedPos = DEFAULT_POSITION
                    if (likelyPos === 'G') mappedPos = 'Goalkeeper'
                    else if (likelyPos === 'D') mappedPos = 'Defender'
                    else if (likelyPos === 'M') mappedPos = 'Midfielder'
                    else if (likelyPos === 'F') mappedPos = 'Attacker'

                    setPosition(mappedPos)
                    const config = METRIC_CONFIG[mappedPos] || METRIC_CONFIG[DEFAULT_POSITION]
                    setSelectedMetrics(config.default)
                }
            }
        } catch (err) {
            console.error('Failed to fetch player data', err)
            setError('Failed to load player data.')
        } finally {
            setLoading(false)
        }
    }

    const toggleMetric = (metricKey) => {
        setSelectedMetrics(prev => {
            if (prev.includes(metricKey)) {
                return prev.filter(k => k !== metricKey)
            }
            return [...prev, metricKey]
        })
    }

    // Handle parent club click to show other loanees
    const handleParentClubClick = async () => {
        // Use primary_team_db_id (database ID) for API calls
        if (!profile?.primary_team_db_id) return
        
        setDrawerOpen(true)
        setLoadingTeamPlayers(true)
        
        try {
            const loans = await APIService.getTeamLoans(profile.primary_team_db_id, {
                active_only: 'true',
                dedupe: 'true'
            })
            // Filter out current player
            const otherPlayers = loans.filter(loan => loan.player_id !== parseInt(playerId))
            setTeamPlayers(otherPlayers)
        } catch (err) {
            console.error('Failed to load team players:', err)
            setTeamPlayers([])
        } finally {
            setLoadingTeamPlayers(false)
        }
    }

    // Format data for charts
    const chartData = stats.map((s) => {
        const point = {
            date: s.fixture_date ? format(new Date(s.fixture_date), 'MMM d') : 'N/A',
            rating: s.rating ? parseFloat(s.rating) : null,
            minutes: s.minutes || 0,
            opponent: s.opponent,
            is_home: s.is_home,
            competition: s.competition,
            fullDate: s.fixture_date,
            loan_team_name: s.loan_team_name,
            loan_window: s.loan_window,
        }

        const getVal = (obj, path) => {
            return path.split('.').reduce((acc, part) => acc && acc[part], obj)
        }

        point['goals'] = s.goals || 0
        point['assists'] = s.assists || 0
        point['saves'] = s.saves || 0
        point['shots_total'] = getVal(s, 'shots.total') || 0
        point['shots_on'] = getVal(s, 'shots.on') || 0
        point['passes_total'] = getVal(s, 'passes.total') || 0
        point['passes_key'] = getVal(s, 'passes.key') || 0
        point['tackles_total'] = getVal(s, 'tackles.total') || 0
        point['blocks'] = getVal(s, 'tackles.blocks') || 0
        point['interceptions'] = getVal(s, 'tackles.interceptions') || 0
        point['duels_won'] = getVal(s, 'duels.won') || 0
        point['dribbles_success'] = getVal(s, 'dribbles.success') || 0

        const config = METRIC_CONFIG[position] || METRIC_CONFIG[DEFAULT_POSITION]
        config.options.forEach(opt => {
            if (point[opt.key] === undefined) {
                point[opt.key] = 0
            }
        })

        return point
    })

    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length) {
            const data = payload[0].payload
            return (
                <div className="bg-white p-3 border rounded-lg shadow-lg text-xs z-50">
                    <p className="font-bold">{data.opponent} ({data.is_home ? 'H' : 'A'})</p>
                    <p className="text-gray-500">{label}</p>
                    {data.loan_team_name && (
                        <p className="text-blue-600 text-xs mb-1">
                            for {data.loan_team_name}
                            {data.loan_window && data.loan_window !== 'Summer' && ` (${data.loan_window})`}
                        </p>
                    )}
                    {payload.map((p, i) => (
                        <p key={i} style={{ color: p.color }} className="font-semibold">
                            {p.name}: {p.value}
                        </p>
                    ))}
                    <p className="text-gray-400 italic mt-1">{data.competition}</p>
                </div>
            )
        }
        return null
    }

    const currentConfig = METRIC_CONFIG[position] || METRIC_CONFIG[DEFAULT_POSITION]
    const playerName = profile?.name || `Player #${playerId}`

    // Calculate season totals - prefer API season stats, fallback to calculated from match data
    const seasonTotals = {
        minutes: seasonStats?.minutes ?? stats.reduce((acc, s) => acc + (s.minutes || 0), 0),
        goals: seasonStats?.goals ?? stats.reduce((acc, s) => acc + (s.goals || 0), 0),
        assists: seasonStats?.assists ?? stats.reduce((acc, s) => acc + (s.assists || 0), 0),
        avgRating: seasonStats?.avg_rating ?? (stats.filter(s => s.rating).length > 0
            ? (stats.reduce((acc, s) => acc + (parseFloat(s.rating) || 0), 0) / stats.filter(s => s.rating).length).toFixed(2)
            : '-'),
        appearances: seasonStats?.appearances ?? stats.length,
        // Goalkeeper stats
        saves: seasonStats?.saves ?? stats.reduce((acc, s) => acc + (s.saves || 0), 0),
        goalsConceded: seasonStats?.goals_conceded ?? stats.reduce((acc, s) => acc + (s.goals_conceded || 0), 0),
        cleanSheets: seasonStats?.clean_sheets ?? 0,
    }

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-slate-50 to-slate-100">
                <div className="text-center">
                    <Loader2 className="h-12 w-12 animate-spin text-blue-500 mx-auto mb-4" />
                    <p className="text-gray-500">Loading player data...</p>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-slate-50 to-slate-100">
                <Card className="max-w-md">
                    <CardContent className="pt-6 text-center">
                        <p className="text-red-500 mb-4">{error}</p>
                        <Button variant="outline" onClick={handleBack}>
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Go Back
                        </Button>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
            {/* Header */}
            <div className="bg-white border-b sticky top-0 z-10">
                <div className="max-w-6xl mx-auto px-4 py-4">
                    <div className="flex items-center gap-4">
                        <Button variant="ghost" size="sm" onClick={handleBack}>
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back
                        </Button>
                        <div className="flex items-center gap-4">
                            {profile?.photo ? (
                                <img 
                                    src={profile.photo} 
                                    alt={playerName}
                                    className="w-16 h-16 rounded-full object-cover border-2 border-gray-200 shadow-md"
                                />
                            ) : (
                                <div className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-md">
                                    <User className="h-8 w-8 text-white" />
                                </div>
                            )}
                            <div>
                                <h1 className="text-2xl font-bold text-gray-900">{playerName}</h1>
                                <div className="flex flex-wrap items-center gap-2 mt-1">
                                    <Badge variant="secondary">{position}</Badge>
                                    {profile?.age && (
                                        <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                                            {profile.age} yrs
                                        </Badge>
                                    )}
                                    {profile?.nationality && (
                                        <Badge variant="outline" className="text-gray-600">{profile.nationality}</Badge>
                                    )}
                                </div>
                                {/* Club Info */}
                                <div className="flex flex-wrap items-center gap-3 mt-2 text-sm">
                                    {profile?.parent_team_name && (
                                        <button
                                            onClick={handleParentClubClick}
                                            className="flex items-center gap-1.5 text-gray-600 hover:text-blue-600 transition-colors cursor-pointer group"
                                        >
                                            {profile.parent_team_logo && (
                                                <img src={profile.parent_team_logo} alt="" className="w-5 h-5 rounded-full object-cover" />
                                            )}
                                            <span className="font-medium group-hover:underline">{profile.parent_team_name}</span>
                                            <Users className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-blue-500" />
                                        </button>
                                    )}
                                    {/* Show loan history if multiple clubs */}
                                    {profile?.loan_history && profile.loan_history.length > 0 && (
                                        <>
                                            <span className="text-gray-400">→</span>
                                            <div className="flex flex-wrap items-center gap-2">
                                                {profile.loan_history.map((loan, idx) => (
                                                    <div 
                                                        key={idx} 
                                                        className={`flex items-center gap-1.5 ${loan.is_active ? 'text-blue-600' : 'text-gray-400'}`}
                                                    >
                                                        {loan.loan_team_logo && (
                                                            <img 
                                                                src={loan.loan_team_logo} 
                                                                alt="" 
                                                                className={`w-5 h-5 rounded-full object-cover ${!loan.is_active ? 'opacity-50' : ''}`} 
                                                            />
                                                        )}
                                                        <span className={`font-medium ${!loan.is_active ? 'line-through' : ''}`}>
                                                            {loan.loan_team_name}
                                                        </span>
                                                        <Badge 
                                                            variant="outline" 
                                                            className={`text-xs ${loan.is_active 
                                                                ? 'bg-blue-50 text-blue-700 border-blue-200' 
                                                                : 'bg-gray-50 text-gray-500 border-gray-200'}`}
                                                        >
                                                            {loan.window_type}
                                                        </Badge>
                                                        {idx < profile.loan_history.length - 1 && (
                                                            <span className="text-gray-300 ml-1">→</span>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </>
                                    )}
                                    {/* Fallback if no loan history */}
                                    {(!profile?.loan_history || profile.loan_history.length === 0) && profile?.loan_team_name && (
                                        <>
                                            <span className="text-gray-400">→</span>
                                            <div className="flex items-center gap-1.5 text-blue-600">
                                                {profile.loan_team_logo && (
                                                    <img src={profile.loan_team_logo} alt="" className="w-5 h-5 rounded-full object-cover" />
                                                )}
                                                <span className="font-medium">{profile.loan_team_name}</span>
                                                <Badge variant="outline" className="text-xs bg-blue-50 text-blue-700 border-blue-200">Loan</Badge>
                                            </div>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="max-w-6xl mx-auto px-4 py-6">
                {stats.length === 0 ? (
                    <Card>
                        <CardContent className="py-12 text-center">
                            <Target className="h-12 w-12 mx-auto text-gray-300 mb-4" />
                            <p className="text-gray-500">No match data available for this player yet.</p>
                        </CardContent>
                    </Card>
                ) : (
                    <div className="space-y-6">
                        {/* Season Summary Cards - Position-aware */}
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                            <Card>
                                <CardContent className="pt-4 text-center">
                                    <div className="text-3xl font-bold text-gray-900">{seasonTotals.appearances}</div>
                                    <div className="text-xs text-gray-500 uppercase tracking-wider mt-1">Appearances</div>
                                </CardContent>
                            </Card>
                            <Card>
                                <CardContent className="pt-4 text-center">
                                    <div className="text-3xl font-bold text-gray-900">{seasonTotals.minutes}</div>
                                    <div className="text-xs text-gray-500 uppercase tracking-wider mt-1">Minutes</div>
                                </CardContent>
                            </Card>
                            {position === 'Goalkeeper' ? (
                                <>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-blue-600">{seasonTotals.saves}</div>
                                            <div className="text-xs text-gray-500 uppercase tracking-wider mt-1">Saves</div>
                                        </CardContent>
                                    </Card>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-orange-600">{seasonTotals.goalsConceded}</div>
                                            <div className="text-xs text-gray-500 uppercase tracking-wider mt-1">Conceded</div>
                                        </CardContent>
                                    </Card>
                                </>
                            ) : (
                                <>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-blue-600">{seasonTotals.goals}</div>
                                            <div className="text-xs text-gray-500 uppercase tracking-wider mt-1">Goals</div>
                                        </CardContent>
                                    </Card>
                                    <Card>
                                        <CardContent className="pt-4 text-center">
                                            <div className="text-3xl font-bold text-green-600">{seasonTotals.assists}</div>
                                            <div className="text-xs text-gray-500 uppercase tracking-wider mt-1">Assists</div>
                                        </CardContent>
                                    </Card>
                                </>
                            )}
                            <Card>
                                <CardContent className="pt-4 text-center">
                                    <div className="text-3xl font-bold text-purple-600">{seasonTotals.avgRating}</div>
                                    <div className="text-xs text-gray-500 uppercase tracking-wider mt-1">Avg Rating</div>
                                </CardContent>
                            </Card>
                        </div>

                        {/* Per-Club Breakdown (if multiple clubs) */}
                        {seasonStats?.clubs && seasonStats.clubs.length > 1 && (
                            <Card>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-base flex items-center gap-2">
                                        <Calendar className="h-4 w-4" />
                                        Stats by Club
                                    </CardTitle>
                                    <CardDescription>Season breakdown across loan destinations</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        {seasonStats.clubs.map((club, idx) => (
                                            <div 
                                                key={idx} 
                                                className={`p-4 rounded-lg border ${club.is_current ? 'bg-blue-50 border-blue-200' : 'bg-gray-50 border-gray-200'}`}
                                            >
                                                <div className="flex items-center gap-2 mb-3">
                                                    {club.team_logo && (
                                                        <img src={club.team_logo} alt="" className="w-6 h-6 rounded-full" />
                                                    )}
                                                    <span className="font-semibold">{club.team_name}</span>
                                                    <Badge 
                                                        variant="outline" 
                                                        className={`text-xs ${club.is_current 
                                                            ? 'bg-blue-100 text-blue-700 border-blue-300' 
                                                            : 'bg-gray-100 text-gray-600 border-gray-300'}`}
                                                    >
                                                        {club.window_type}
                                                    </Badge>
                                                </div>
                                                <div className="grid grid-cols-4 gap-3 text-center">
                                                    <div>
                                                        <div className="text-lg font-bold text-gray-900">{club.appearances}</div>
                                                        <div className="text-xs text-gray-500">Apps</div>
                                                    </div>
                                                    <div>
                                                        <div className="text-lg font-bold text-gray-900">{club.minutes}</div>
                                                        <div className="text-xs text-gray-500">Mins</div>
                                                    </div>
                                                    {position === 'Goalkeeper' ? (
                                                        <>
                                                            <div>
                                                                <div className="text-lg font-bold text-blue-600">{club.saves ?? 0}</div>
                                                                <div className="text-xs text-gray-500">Saves</div>
                                                            </div>
                                                            <div>
                                                                <div className="text-lg font-bold text-orange-600">{club.goals_conceded ?? 0}</div>
                                                                <div className="text-xs text-gray-500">Conceded</div>
                                                            </div>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <div>
                                                                <div className="text-lg font-bold text-blue-600">{club.goals}</div>
                                                                <div className="text-xs text-gray-500">Goals</div>
                                                            </div>
                                                            <div>
                                                                <div className="text-lg font-bold text-green-600">{club.assists}</div>
                                                                <div className="text-xs text-gray-500">Assists</div>
                                                            </div>
                                                        </>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        {/* Tabs for Charts and Match Log */}
                        <Card>
                            <Tabs defaultValue="charts">
                                <CardHeader className="pb-0">
                                    <div className="flex items-center justify-between">
                                        <CardTitle className="flex items-center gap-2">
                                            <TrendingUp className="h-5 w-5" />
                                            Performance Analysis
                                        </CardTitle>
                                        <TabsList>
                                            <TabsTrigger value="charts">Charts</TabsTrigger>
                                            <TabsTrigger value="matches">Match Log</TabsTrigger>
                                        </TabsList>
                                    </div>
                                </CardHeader>
                                <CardContent className="pt-6">
                                    <TabsContent value="charts" className="mt-0">
                                        <div className="space-y-6">
                                            {/* Metrics Selector */}
                                            <div className="p-4 bg-gray-50 rounded-lg">
                                                <h3 className="text-sm font-medium mb-3 text-gray-700">Select Metrics to Compare</h3>
                                                <div className="flex flex-wrap gap-2">
                                                    {currentConfig.options.map(opt => (
                                                        <button
                                                            key={opt.key}
                                                            onClick={() => toggleMetric(opt.key)}
                                                            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${selectedMetrics.includes(opt.key)
                                                                ? 'bg-blue-50 border-blue-200 text-blue-700 ring-1 ring-blue-200'
                                                                : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                                                                }`}
                                                        >
                                                            <span 
                                                                className={`inline-block w-2 h-2 rounded-full mr-2 ${selectedMetrics.includes(opt.key) ? '' : 'bg-gray-300'}`} 
                                                                style={{ backgroundColor: selectedMetrics.includes(opt.key) ? opt.color : undefined }}
                                                            />
                                                            {opt.label}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>

                                            {/* Main Performance Chart */}
                                            <div>
                                                <h3 className="text-sm font-medium mb-4 text-gray-700">Performance Trends</h3>
                                                <div className="h-[300px] w-full">
                                                    <ResponsiveContainer width="100%" height="100%">
                                                        <LineChart data={chartData}>
                                                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                                                            <XAxis
                                                                dataKey="date"
                                                                tick={{ fontSize: 10, fill: '#6b7280' }}
                                                                interval="preserveStartEnd"
                                                                tickLine={false}
                                                                axisLine={false}
                                                            />
                                                            <YAxis
                                                                tick={{ fontSize: 10, fill: '#6b7280' }}
                                                                tickLine={false}
                                                                axisLine={false}
                                                            />
                                                            <Tooltip content={<CustomTooltip />} />
                                                            {currentConfig.options.filter(opt => selectedMetrics.includes(opt.key)).map(opt => (
                                                                <Line
                                                                    key={opt.key}
                                                                    type="monotone"
                                                                    dataKey={opt.key}
                                                                    stroke={opt.color}
                                                                    strokeWidth={2}
                                                                    dot={{ r: 3, fill: opt.color, strokeWidth: 0 }}
                                                                    activeDot={{ r: 6, strokeWidth: 0 }}
                                                                    name={opt.label}
                                                                />
                                                            ))}
                                                        </LineChart>
                                                    </ResponsiveContainer>
                                                </div>
                                            </div>

                                            {/* Rating & Minutes Charts Side by Side */}
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                                <div>
                                                    <h3 className="text-sm font-medium mb-4 text-gray-700">Match Ratings</h3>
                                                    <div className="h-[200px] w-full">
                                                        <ResponsiveContainer width="100%" height="100%">
                                                            <LineChart data={chartData}>
                                                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                                                                <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" tickLine={false} axisLine={false} />
                                                                <YAxis domain={[0, 10]} tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
                                                                <Tooltip content={<CustomTooltip />} />
                                                                <ReferenceLine y={7} stroke="#16a34a" strokeDasharray="3 3" label={{ value: 'Good (7.0)', position: 'insideTopRight', fontSize: 10, fill: '#16a34a' }} />
                                                                <Line type="monotone" dataKey="rating" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} name="Rating" />
                                                            </LineChart>
                                                        </ResponsiveContainer>
                                                    </div>
                                                </div>

                                                <div>
                                                    <h3 className="text-sm font-medium mb-4 text-gray-700">Minutes Played</h3>
                                                    <div className="h-[200px] w-full">
                                                        <ResponsiveContainer width="100%" height="100%">
                                                            <BarChart data={chartData}>
                                                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                                                                <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" tickLine={false} axisLine={false} />
                                                                <YAxis domain={[0, 90]} tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
                                                                <Tooltip content={<CustomTooltip />} />
                                                                <Bar dataKey="minutes" fill="#0f172a" radius={[4, 4, 0, 0]} name="Minutes" />
                                                            </BarChart>
                                                        </ResponsiveContainer>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </TabsContent>

                                    <TabsContent value="matches" className="mt-0">
                                        <ScrollArea className="h-[500px]">
                                            <table className="w-full text-sm text-left">
                                                <thead className="bg-gray-50 sticky top-0">
                                                    <tr>
                                                        <th className="p-3 font-medium text-gray-500">Date</th>
                                                        <th className="p-3 font-medium text-gray-500">Club</th>
                                                        <th className="p-3 font-medium text-gray-500">Match</th>
                                                        <th className="p-3 font-medium text-gray-500">Min</th>
                                                        <th className="p-3 font-medium text-gray-500">Rating</th>
                                                        <th className="p-3 font-medium text-gray-500">{position === 'Goalkeeper' ? 'Saves/GA' : 'G/A'}</th>
                                                        <th className="p-3 font-medium text-gray-500">Key Stats</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y">
                                                    {stats.slice().reverse().map((s, i) => (
                                                        <tr key={i} className="hover:bg-gray-50">
                                                            <td className="p-3 whitespace-nowrap">
                                                                {s.fixture_date ? format(new Date(s.fixture_date), 'MMM d, yyyy') : '-'}
                                                            </td>
                                                            <td className="p-3">
                                                                <div className="flex items-center gap-1.5">
                                                                    {s.loan_team_logo && (
                                                                        <img src={s.loan_team_logo} alt="" className="w-4 h-4 rounded-full" />
                                                                    )}
                                                                    <span className="text-xs text-gray-600 font-medium truncate max-w-[80px]">
                                                                        {s.loan_team_name || 'Unknown'}
                                                                    </span>
                                                                </div>
                                                                {s.loan_window && s.loan_window !== 'Summer' && (
                                                                    <Badge variant="outline" className="text-xs mt-0.5 bg-orange-50 text-orange-600 border-orange-200">
                                                                        {s.loan_window}
                                                                    </Badge>
                                                                )}
                                                            </td>
                                                            <td className="p-3">
                                                                <div className="font-medium">{s.opponent}</div>
                                                                <div className="text-xs text-gray-500">{s.competition}</div>
                                                            </td>
                                                            <td className="p-3">{s.minutes}'</td>
                                                            <td className="p-3">
                                                                <span className={`px-2 py-1 rounded text-xs font-medium ${parseFloat(s.rating) >= 7.5 ? 'bg-green-100 text-green-700' :
                                                                    parseFloat(s.rating) >= 6.0 ? 'bg-gray-100 text-gray-700' :
                                                                        'bg-red-50 text-red-700'
                                                                    }`}>
                                                                    {s.rating || '-'}
                                                                </span>
                                                            </td>
                                                            <td className="p-3">
                                                                {position === 'Goalkeeper' ? (
                                                                    <>
                                                                        {s.saves > 0 && <span className="mr-2">🧤 {s.saves}</span>}
                                                                        {s.goals_conceded > 0 && <span className="text-orange-600">{s.goals_conceded} GA</span>}
                                                                        {s.goals_conceded === 0 && <span className="text-green-600">CS</span>}
                                                                        {!s.saves && s.goals_conceded === undefined && <span className="text-gray-300">-</span>}
                                                                    </>
                                                                ) : (
                                                                    <>
                                                                        {s.goals > 0 && <span className="mr-2">⚽ {s.goals}</span>}
                                                                        {s.assists > 0 && <span>🅰️ {s.assists}</span>}
                                                                        {s.goals === 0 && s.assists === 0 && <span className="text-gray-300">-</span>}
                                                                    </>
                                                                )}
                                                            </td>
                                                            <td className="p-3 text-xs text-gray-500">
                                                                {s.passes?.key > 0 && <div>{s.passes.key} Key Passes</div>}
                                                                {s.tackles?.total > 0 && <div>{s.tackles.total} Tackles</div>}
                                                                {s.dribbles?.success > 0 && <div>{s.dribbles.success} Dribbles</div>}
                                                                {s.saves > 0 && <div>{s.saves} Saves</div>}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </ScrollArea>
                                    </TabsContent>
                                </CardContent>
                            </Tabs>
                        </Card>

                        {/* Writer Coverage Section */}
                        {commentaries.total_count > 0 && (
                            <Card>
                                <CardHeader>
                                    <CardTitle className="flex items-center gap-2">
                                        <PenTool className="h-5 w-5" />
                                        Writer Coverage
                                    </CardTitle>
                                    <CardDescription>
                                        {commentaries.total_count} writeup{commentaries.total_count !== 1 ? 's' : ''} from {commentaries.authors.length} journalist{commentaries.authors.length !== 1 ? 's' : ''}
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    {/* Featured Authors */}
                                    <div className="mb-6">
                                        <h3 className="text-sm font-medium text-gray-700 mb-3">Writers covering this player</h3>
                                        <div className="flex flex-wrap gap-3">
                                            {commentaries.authors.map((author) => (
                                                <Link 
                                                    key={author.id}
                                                    to={`/journalists/${author.id}`}
                                                    className="flex items-center gap-2 px-3 py-2 bg-gray-50 hover:bg-gray-100 rounded-lg transition-colors group"
                                                >
                                                    <Avatar className="h-8 w-8">
                                                        <AvatarImage src={author.profile_image_url} alt={author.display_name} />
                                                        <AvatarFallback className="text-xs bg-blue-100 text-blue-700">
                                                            {author.display_name?.charAt(0) || 'W'}
                                                        </AvatarFallback>
                                                    </Avatar>
                                                    <div className="text-left">
                                                        <div className="text-sm font-medium text-gray-900 group-hover:text-blue-600 transition-colors">
                                                            {author.display_name}
                                                        </div>
                                                        <div className="text-xs text-gray-500">
                                                            {author.commentary_count} writeup{author.commentary_count !== 1 ? 's' : ''}
                                                        </div>
                                                    </div>
                                                    <ChevronRight className="h-4 w-4 text-gray-400 group-hover:text-blue-500 transition-colors" />
                                                </Link>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Recent Writeups */}
                                    <div>
                                        <h3 className="text-sm font-medium text-gray-700 mb-3">Recent writeups</h3>
                                        <div className="space-y-3">
                                            {commentaries.commentaries.slice(0, 5).map((commentary) => (
                                                <Link 
                                                    key={commentary.id}
                                                    to={`/writeups/${commentary.id}`}
                                                    className="block p-4 bg-gray-50 hover:bg-gray-100 rounded-lg transition-colors group"
                                                >
                                                    <div className="flex items-start gap-3">
                                                        {commentary.author && (
                                                            <Avatar className="h-10 w-10 flex-shrink-0">
                                                                <AvatarImage src={commentary.author.profile_image_url} alt={commentary.author.display_name} />
                                                                <AvatarFallback className="text-sm bg-blue-100 text-blue-700">
                                                                    {commentary.author.display_name?.charAt(0) || 'W'}
                                                                </AvatarFallback>
                                                            </Avatar>
                                                        )}
                                                        <div className="flex-1 min-w-0">
                                                            <div className="flex items-center gap-2 mb-1">
                                                                <span className="font-medium text-gray-900 group-hover:text-blue-600 transition-colors">
                                                                    {commentary.author?.display_name || 'Anonymous'}
                                                                </span>
                                                                {commentary.is_premium && (
                                                                    <Badge variant="secondary" className="text-xs bg-amber-100 text-amber-700 border-amber-200">
                                                                        Premium
                                                                    </Badge>
                                                                )}
                                                            </div>
                                                            {commentary.title && (
                                                                <div className="text-sm font-medium text-gray-800 mb-1">{commentary.title}</div>
                                                            )}
                                                            <div className="text-sm text-gray-600 line-clamp-2">
                                                                {commentary.content?.substring(0, 150)}...
                                                            </div>
                                                            <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
                                                                {commentary.newsletter && (
                                                                    <span>{commentary.newsletter.team_name}</span>
                                                                )}
                                                                {commentary.created_at && (
                                                                    <>
                                                                        <span>·</span>
                                                                        <span>{format(new Date(commentary.created_at), 'MMM d, yyyy')}</span>
                                                                    </>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <ChevronRight className="h-5 w-5 text-gray-400 group-hover:text-blue-500 transition-colors flex-shrink-0" />
                                                    </div>
                                                </Link>
                                            ))}
                                        </div>
                                        {commentaries.total_count > 5 && (
                                            <div className="mt-4 text-center">
                                                <span className="text-sm text-gray-500">
                                                    Showing 5 of {commentaries.total_count} writeups
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>
                        )}
                    </div>
                )}
            </div>

            {/* Team Players Drawer */}
            <Drawer open={drawerOpen} onOpenChange={setDrawerOpen}>
                <DrawerContent>
                    <DrawerHeader className="border-b">
                        <div className="flex items-center gap-3">
                            {profile?.parent_team_logo && (
                                <img 
                                    src={profile.parent_team_logo} 
                                    alt="" 
                                    className="w-10 h-10 rounded-full object-cover border-2 border-gray-200" 
                                />
                            )}
                            <div>
                                <DrawerTitle>{profile?.parent_team_name} Loanees</DrawerTitle>
                                <DrawerDescription>
                                    {teamPlayers.length} player{teamPlayers.length !== 1 ? 's' : ''} currently out on loan
                                </DrawerDescription>
                            </div>
                        </div>
                    </DrawerHeader>
                    
                    <div className="p-4 max-h-[60vh] overflow-y-auto">
                        {loadingTeamPlayers ? (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
                            </div>
                        ) : teamPlayers.length === 0 ? (
                            <p className="text-center text-gray-500 py-8">No other players on loan</p>
                        ) : (
                            <div className="space-y-2">
                                {teamPlayers.map((player) => (
                                    <Link
                                        key={player.player_id}
                                        to={`/players/${player.player_id}`}
                                        onClick={() => setDrawerOpen(false)}
                                        className="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50 active:bg-gray-100 transition-colors group"
                                    >
                                        {player.player_photo ? (
                                            <img 
                                                src={player.player_photo} 
                                                alt={player.player_name}
                                                className="w-12 h-12 rounded-full object-cover border-2 border-gray-200"
                                            />
                                        ) : (
                                            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center flex-shrink-0">
                                                <User className="h-6 w-6 text-white" />
                                            </div>
                                        )}
                                        <div className="flex-1 min-w-0">
                                            <div className="font-medium text-gray-900 group-hover:text-blue-600 transition-colors">
                                                {player.player_name}
                                            </div>
                                            <div className="flex items-center gap-2 text-sm text-gray-500">
                                                {player.loan_team_logo && (
                                                    <img src={player.loan_team_logo} alt="" className="w-4 h-4 rounded-full" />
                                                )}
                                                <span className="truncate">{player.loan_team_name}</span>
                                            </div>
                                            {(player.appearances > 0 || player.goals > 0 || player.assists > 0 || player.saves > 0) && (
                                                <div className="text-xs text-gray-400 mt-0.5">
                                                    {player.appearances || 0} apps · {player.position === 'G' || player.position === 'Goalkeeper' 
                                                        ? `${player.saves || 0} saves · ${player.goals_conceded || 0} GA`
                                                        : `${player.goals || 0}G · ${player.assists || 0}A`}
                                                </div>
                                            )}
                                        </div>
                                        <ChevronRight className="h-5 w-5 text-gray-300 group-hover:text-blue-500 transition-colors flex-shrink-0" />
                                    </Link>
                                ))}
                            </div>
                        )}
                    </div>
                </DrawerContent>
            </Drawer>
        </div>
    )
}

export default PlayerPage

