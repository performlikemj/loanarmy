import React, { useState, useEffect } from 'react'
import {
    Drawer,
    DrawerContent,
    DrawerHeader,
    DrawerTitle,
    DrawerDescription,
    DrawerFooter,
    DrawerClose,
} from '@/components/ui/drawer'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
import { Loader2, X } from 'lucide-react'
import { APIService } from '@/lib/api'
import { format } from 'date-fns'

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

export function PlayerStatsDrawer({ playerId, isOpen, onClose, playerName }) {
    const [stats, setStats] = useState([])
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [position, setPosition] = useState(DEFAULT_POSITION)
    const [selectedMetrics, setSelectedMetrics] = useState([])
    const [selectedFixture, setSelectedFixture] = useState(null)

    useEffect(() => {
        if (isOpen && playerId) {
            fetchStats()
        } else {
            setStats([])
            setError(null)
            setSelectedMetrics([])
        }
    }, [isOpen, playerId])

    const fetchStats = async () => {
        setLoading(true)
        setError(null)
        try {
            const data = await APIService.getPlayerStats(playerId)
            setStats(data || [])

            // Infer position
            if (data && data.length > 0) {
                const positions = data.map(s => s.position).filter(Boolean)
                if (positions.length > 0) {
                    // Simple mode: just take the most recent non-null position
                    // Or could do frequency map. Let's do most frequent.
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

                    // Set default metrics for this position
                    const config = METRIC_CONFIG[mappedPos] || METRIC_CONFIG[DEFAULT_POSITION]
                    setSelectedMetrics(config.default)
                }
            }
        } catch (err) {
            console.error('Failed to fetch player stats', err)
            setError('Failed to load player statistics.')
        } finally {
            setLoading(false)
        }
    }

    const toggleMetric = (metricKey) => {
        setSelectedMetrics(prev => {
            if (prev.includes(metricKey)) {
                return prev.filter(k => k !== metricKey)
            }
            if (prev.length >= 3) {
                // Limit to 3 for readability? Optional. Let's allow more but maybe warn?
                // Actually let's just allow it.
                return [...prev, metricKey]
            }
            return [...prev, metricKey]
        })
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
        }

        // Helper to safely get nested values
        const getVal = (obj, path) => {
            return path.split('.').reduce((acc, part) => acc && acc[part], obj)
        }

        // Flatten stats for easy charting
        // Map nested API response to flat keys used in METRIC_CONFIG
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

        // Ensure all configured options have a value
        const config = METRIC_CONFIG[position] || METRIC_CONFIG[DEFAULT_POSITION]
        config.options.forEach(opt => {
            if (point[opt.key] === undefined) {
                point[opt.key] = 0
            }
        })

        return point
    })

    const handleChartClick = (data) => {
        if (data && data.activePayload && data.activePayload.length > 0) {
            const payload = data.activePayload[0].payload
            // Find original stat object
            const originalStat = stats.find(s => s.fixture_date === payload.fullDate)
            if (originalStat) {
                setSelectedFixture(originalStat)
            }
        }
    }

    const handleRowClick = (stat) => {
        setSelectedFixture(stat)
    }

    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length) {
            const data = payload[0].payload
            return (
                <div className="bg-white p-3 border rounded shadow-lg text-xs z-50">
                    <p className="font-bold">{data.opponent} ({data.is_home ? 'H' : 'A'})</p>
                    <p className="text-gray-500">{label}</p>
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

    return (
        <Drawer open={isOpen} onOpenChange={onClose}>
            <DrawerContent className="h-[90vh]">
                <div className="mx-auto w-full max-w-5xl h-full flex flex-col">
                    <DrawerHeader className="flex-none border-b pb-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <DrawerTitle className="text-xl">Player Analysis: {playerName}</DrawerTitle>
                                <DrawerDescription className="flex items-center gap-2 mt-1">
                                    <span className="bg-blue-100 text-blue-800 text-xs px-2 py-0.5 rounded font-medium">
                                        {position}
                                    </span>
                                    <span>Performance metrics and historical data.</span>
                                </DrawerDescription>
                            </div>
                            <DrawerClose asChild>
                                <Button variant="ghost" size="icon">
                                    <X className="h-4 w-4" />
                                </Button>
                            </DrawerClose>
                        </div>
                    </DrawerHeader>

                    <div className="flex-1 overflow-hidden p-4 bg-gray-50/50">
                        {loading ? (
                            <div className="h-full flex items-center justify-center">
                                <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
                            </div>
                        ) : error ? (
                            <div className="h-full flex items-center justify-center text-red-500">
                                {error}
                            </div>
                        ) : stats.length === 0 ? (
                            <div className="h-full flex items-center justify-center text-gray-500">
                                No stats available for this player.
                            </div>
                        ) : (
                            <Tabs defaultValue="charts" className="h-full flex flex-col">
                                <div className="flex items-center justify-between mb-4 flex-none">
                                    <TabsList>
                                        <TabsTrigger value="charts">Visualizations</TabsTrigger>
                                        <TabsTrigger value="table">Match Log</TabsTrigger>
                                    </TabsList>
                                </div>

                                <TabsContent value="charts" className="flex-1 overflow-y-auto pr-2">
                                    <div className="space-y-6 pb-8">

                                        {/* Metrics Selector */}
                                        <div className="bg-white p-4 rounded-lg border shadow-sm">
                                            <h3 className="text-sm font-medium mb-3 text-gray-700">Select Metrics</h3>
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
                                                        <span className={`inline-block w-2 h-2 rounded-full mr-2 ${selectedMetrics.includes(opt.key) ? '' : 'bg-gray-300'}`} style={{ backgroundColor: selectedMetrics.includes(opt.key) ? opt.color : undefined }}></span>
                                                        {opt.label}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>

                                        {/* Main Chart */}
                                        <div className="bg-white p-4 rounded-lg border shadow-sm">
                                            <h3 className="text-sm font-medium mb-4 text-gray-700">Performance Trends</h3>
                                            <div className="h-[300px] w-full">
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <LineChart data={chartData} onClick={handleChartClick} className="cursor-pointer">
                                                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                                                        <XAxis
                                                            dataKey="date"
                                                            tick={{ fontSize: 10, fill: '#6b7280' }}
                                                            interval="preserveStartEnd"
                                                            tickLine={false}
                                                            axisLine={false}
                                                            dy={10}
                                                        />
                                                        <YAxis
                                                            hide={false}
                                                            tick={{ fontSize: 10, fill: '#6b7280' }}
                                                            tickLine={false}
                                                            axisLine={false}
                                                            dx={-10}
                                                        />
                                                        <Tooltip content={<CustomTooltip />} cursor={{ stroke: '#9ca3af', strokeWidth: 1, strokeDasharray: '4 4' }} />

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

                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                            {/* Rating History */}
                                            <div className="bg-white p-4 rounded-lg border shadow-sm">
                                                <h3 className="text-sm font-medium mb-4 text-gray-700">Match Ratings</h3>
                                                <div className="h-[200px] w-full">
                                                    <ResponsiveContainer width="100%" height="100%">
                                                        <LineChart data={chartData} onClick={handleChartClick} className="cursor-pointer">
                                                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                                                            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" tickLine={false} axisLine={false} />
                                                            <YAxis domain={[0, 10]} hide={false} tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} />
                                                            <Tooltip content={<CustomTooltip />} />
                                                            <ReferenceLine y={7} stroke="#16a34a" strokeDasharray="3 3" label={{ value: 'Good (7.0)', position: 'insideTopRight', fontSize: 10, fill: '#16a34a' }} />
                                                            <Line type="monotone" dataKey="rating" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} name="Rating" />
                                                        </LineChart>
                                                    </ResponsiveContainer>
                                                </div>
                                            </div>

                                            {/* Minutes Played */}
                                            <div className="bg-white p-4 rounded-lg border shadow-sm">
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

                                        {/* Key Stats Summary */}
                                        <div className="bg-white p-4 rounded-lg border shadow-sm">
                                            <h3 className="text-sm font-medium mb-4 text-gray-700">Season Totals</h3>
                                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                                                <div className="p-3 bg-gray-50 rounded text-center">
                                                    <div className="text-2xl font-bold text-gray-900">{stats.reduce((acc, s) => acc + (s.minutes || 0), 0)}</div>
                                                    <div className="text-xs text-gray-500 uppercase tracking-wider">Minutes</div>
                                                </div>
                                                <div className="p-3 bg-gray-50 rounded text-center">
                                                    <div className="text-2xl font-bold text-gray-900">{stats.reduce((acc, s) => acc + (s.goals || 0), 0)}</div>
                                                    <div className="text-xs text-gray-500 uppercase tracking-wider">Goals</div>
                                                </div>
                                                <div className="p-3 bg-gray-50 rounded text-center">
                                                    <div className="text-2xl font-bold text-gray-900">{stats.reduce((acc, s) => acc + (s.assists || 0), 0)}</div>
                                                    <div className="text-xs text-gray-500 uppercase tracking-wider">Assists</div>
                                                </div>
                                                <div className="p-3 bg-gray-50 rounded text-center">
                                                    <div className="text-2xl font-bold text-gray-900">
                                                        {(stats.reduce((acc, s) => acc + (parseFloat(s.rating) || 0), 0) / (stats.filter(s => s.rating).length || 1)).toFixed(2)}
                                                    </div>
                                                    <div className="text-xs text-gray-500 uppercase tracking-wider">Avg Rating</div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </TabsContent>

                                <TabsContent value="table" className="flex-1 overflow-hidden">
                                    <ScrollArea className="h-full border rounded-md bg-white">
                                        <table className="w-full text-sm text-left">
                                            <thead className="bg-gray-50 sticky top-0 z-10">
                                                <tr>
                                                    <th className="p-3 font-medium text-gray-500">Date</th>
                                                    <th className="p-3 font-medium text-gray-500">Match</th>
                                                    <th className="p-3 font-medium text-gray-500">Min</th>
                                                    <th className="p-3 font-medium text-gray-500">Rating</th>
                                                    <th className="p-3 font-medium text-gray-500">G/A</th>
                                                    <th className="p-3 font-medium text-gray-500">Key Stats</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y">
                                                {stats.map((s, i) => (
                                                    <tr key={i} className="hover:bg-gray-50 cursor-pointer transition-colors" onClick={() => handleRowClick(s)}>
                                                        <td className="p-3 whitespace-nowrap">
                                                            {s.fixture_date ? format(new Date(s.fixture_date), 'MMM d, yyyy') : '-'}
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
                                                            {s.goals > 0 && <span className="mr-2">⚽ {s.goals}</span>}
                                                            {s.assists > 0 && <span>🅰️ {s.assists}</span>}
                                                            {s.goals === 0 && s.assists === 0 && <span className="text-gray-300">-</span>}
                                                        </td>
                                                        <td className="p-3 text-xs text-gray-500">
                                                            {s.passes_key > 0 && <div>{s.passes_key} Key Passes</div>}
                                                            {s.tackles_total > 0 && <div>{s.tackles_total} Tackles</div>}
                                                            {s.dribbles_success > 0 && <div>{s.dribbles_success} Dribbles</div>}
                                                            {s.saves > 0 && <div>{s.saves} Saves</div>}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </ScrollArea>
                                </TabsContent>
                            </Tabs>
                        )}
                    </div>
                </div>
            </DrawerContent>
            <FixtureDetailsDialog
                fixture={selectedFixture}
                isOpen={!!selectedFixture}
                onClose={() => setSelectedFixture(null)}
            />
        </Drawer>
    )
}

function FixtureDetailsDialog({ fixture, isOpen, onClose }) {
    if (!fixture) return null

    // Parse raw_json if available
    let rawStats = null
    try {
        if (fixture.raw_json) {
            rawStats = JSON.parse(fixture.raw_json)
            // If it's wrapped in a list or object structure from API-Football
            if (rawStats.statistics && Array.isArray(rawStats.statistics)) {
                rawStats = rawStats.statistics[0]
            }
        }
    } catch (e) {
        console.error("Failed to parse raw_json", e)
    }

    // Helper to render a stat block
    const renderStatBlock = (title, data) => {
        if (!data) return null
        const entries = Object.entries(data).filter(([_, v]) => v !== null && v !== undefined)
        if (entries.length === 0) return null

        return (
            <div className="bg-gray-50 p-3 rounded-md">
                <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">{title}</h4>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                    {entries.map(([key, value]) => (
                        <div key={key} className="flex justify-between">
                            <span className="text-gray-600 capitalize">{key.replace(/_/g, ' ')}</span>
                            <span className="font-medium text-gray-900">{String(value)}</span>
                        </div>
                    ))}
                </div>
            </div>
        )
    }

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <span>{fixture.opponent}</span>
                        <span className={`text-sm font-normal px-2 py-0.5 rounded ${fixture.is_home ? 'bg-blue-100 text-blue-800' : 'bg-orange-100 text-orange-800'}`}>
                            {fixture.is_home ? 'Home' : 'Away'}
                        </span>
                    </DialogTitle>
                    <DialogDescription>
                        {fixture.competition} • {fixture.fixture_date ? format(new Date(fixture.fixture_date), 'MMMM d, yyyy') : ''}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-6 py-4">
                    {/* Top Level Summary */}
                    <div className="grid grid-cols-4 gap-4 text-center">
                        <div className="p-2 bg-blue-50 rounded">
                            <div className="text-xl font-bold text-blue-700">{fixture.rating || '-'}</div>
                            <div className="text-xs text-blue-600">Rating</div>
                        </div>
                        <div className="p-2 bg-green-50 rounded">
                            <div className="text-xl font-bold text-green-700">{fixture.minutes}'</div>
                            <div className="text-xs text-green-600">Minutes</div>
                        </div>
                        <div className="p-2 bg-purple-50 rounded">
                            <div className="text-xl font-bold text-purple-700">{fixture.goals}</div>
                            <div className="text-xs text-purple-600">Goals</div>
                        </div>
                        <div className="p-2 bg-orange-50 rounded">
                            <div className="text-xl font-bold text-orange-700">{fixture.assists}</div>
                            <div className="text-xs text-orange-600">Assists</div>
                        </div>
                    </div>

                    {rawStats ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {renderStatBlock("Shots", rawStats.shots)}
                            {renderStatBlock("Passes", rawStats.passes)}
                            {renderStatBlock("Tackles", rawStats.tackles)}
                            {renderStatBlock("Duels", rawStats.duels)}
                            {renderStatBlock("Dribbles", rawStats.dribbles)}
                            {renderStatBlock("Defense", {
                                ...rawStats.tackles,
                                blocks: rawStats.tackles?.blocks,
                                interceptions: rawStats.tackles?.interceptions
                            })}
                            {renderStatBlock("Fouls", rawStats.fouls)}
                            {renderStatBlock("Penalty", rawStats.penalty)}
                            {/* Goalkeeper specific */}
                            {rawStats.goals?.saves !== null && renderStatBlock("Goalkeeping", {
                                saves: rawStats.goals?.saves,
                                conceded: rawStats.goals?.conceded
                            })}
                        </div>
                    ) : (
                        <div className="text-center text-gray-500 py-8">
                            Detailed stats not available for this match.
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    )
}
