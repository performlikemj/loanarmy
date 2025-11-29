import React, { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Loader2, Plus, FileText, Users, LogOut, TrendingUp, UserPlus } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { APIService } from '@/lib/api'
import { useAuthUI } from '@/context/AuthContext'

export function WriterDashboard() {
    const navigate = useNavigate()
    const { logout } = useAuthUI()
    const [loading, setLoading] = useState(true)
    const [teams, setTeams] = useState([])
    const [commentaries, setCommentaries] = useState([])
    const [stats, setStats] = useState(null)
    const [error, setError] = useState('')

    useEffect(() => {
        const loadData = async () => {
            try {
                const [teamsData, commentariesData, statsData] = await Promise.all([
                    APIService.getWriterTeams(),
                    APIService.getWriterCommentaries(),
                    APIService.getJournalistOwnStats().catch(() => null) // Graceful fallback
                ])
                setTeams(teamsData || [])
                setCommentaries(commentariesData || [])
                setStats(statsData)
            } catch (err) {
                console.error('Failed to load writer data', err)
                setError('Failed to load dashboard data. Please try again.')
                if (err.status === 401 || err.status === 403) {
                    // Maybe redirect to login if auth failed
                }
            } finally {
                setLoading(false)
            }
        }
        loadData()
    }, [])

    const handleLogout = () => {
        logout()
        navigate('/writer/login')
    }

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-gray-50">
            <header className="bg-white shadow">
                <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8 flex justify-between items-center">
                    <h1 className="text-3xl font-bold text-gray-900">Writer Dashboard</h1>
                    <Button variant="outline" onClick={handleLogout}>
                        <LogOut className="mr-2 h-4 w-4" /> Logout
                    </Button>
                </div>
            </header>
            <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
                <div className="px-4 py-6 sm:px-0 space-y-6">

                    {error && (
                        <div className="p-4 bg-red-50 text-red-700 rounded-md border border-red-200">
                            {error}
                        </div>
                    )}

                    {/* Subscriber Statistics */}
                    {stats && (
                        <>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <Card className="bg-gradient-to-br from-blue-50 to-white border-blue-100">
                                    <CardHeader className="pb-3">
                                        <CardDescription className="flex items-center text-blue-600">
                                            <Users className="h-4 w-4 mr-1" />
                                            Total Subscribers
                                        </CardDescription>
                                        <CardTitle className="text-3xl font-bold text-blue-900">
                                            {stats.total_subscribers || 0}
                                        </CardTitle>
                                    </CardHeader>
                                </Card>

                                <Card className="bg-gradient-to-br from-green-50 to-white border-green-100">
                                    <CardHeader className="pb-3">
                                        <CardDescription className="flex items-center text-green-600">
                                            <TrendingUp className="h-4 w-4 mr-1" />
                                            Last 7 Days
                                        </CardDescription>
                                        <CardTitle className="text-3xl font-bold text-green-900">
                                            +{stats.subscribers_last_7_days || 0}
                                        </CardTitle>
                                    </CardHeader>
                                </Card>

                                <Card className="bg-gradient-to-br from-purple-50 to-white border-purple-100">
                                    <CardHeader className="pb-3">
                                        <CardDescription className="flex items-center text-purple-600">
                                            <UserPlus className="h-4 w-4 mr-1" />
                                            Last 30 Days
                                        </CardDescription>
                                        <CardTitle className="text-3xl font-bold text-purple-900">
                                            +{stats.subscribers_last_30_days || 0}
                                        </CardTitle>
                                    </CardHeader>
                                </Card>
                            </div>

                            {/* Subscriber Growth Chart */}
                            {stats.timeline && stats.timeline.length > 0 && (
                                <Card>
                                    <CardHeader>
                                        <CardTitle>Subscriber Growth</CardTitle>
                                        <CardDescription>Weekly subscriber activity over the last 90 days</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <ResponsiveContainer width="100%" height={300}>
                                            <LineChart data={stats.timeline}>
                                                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200" />
                                                <XAxis
                                                    dataKey="week"
                                                    className="text-xs"
                                                    tickFormatter={(value) => {
                                                        const date = new Date(value)
                                                        return `${date.getMonth() + 1}/${date.getDate()}`
                                                    }}
                                                />
                                                <YAxis className="text-xs" />
                                                <Tooltip
                                                    labelFormatter={(value) => `Week of ${value}`}
                                                    contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.95)', border: '1px solid #e5e7eb', borderRadius: '8px' }}
                                                />
                                                <Line
                                                    type="monotone"
                                                    dataKey="new_subscribers"
                                                    stroke="#3b82f6"
                                                    strokeWidth={2}
                                                    name="New Subscribers"
                                                    dot={{ fill: '#3b82f6', r: 4 }}
                                                />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </CardContent>
                                </Card>
                            )}

                            {/* Team Breakdown */}
                            {stats.team_breakdown && stats.team_breakdown.length > 0 && (
                                <Card>
                                    <CardHeader>
                                        <CardTitle>Subscribers by Team</CardTitle>
                                        <CardDescription>Your subscriber count for each team you cover</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <Table>
                                            <TableHeader>
                                                <TableRow>
                                                    <TableHead>Team</TableHead>
                                                    <TableHead className="text-right">Subscribers</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {stats.team_breakdown.map(team => (
                                                    <TableRow key={team.team_id}>
                                                        <TableCell className="font-medium flex items-center gap-2">
                                                            {team.team_logo && (
                                                                <img src={team.team_logo} alt={team.team_name} className="h-6 w-6 object-contain" />
                                                            )}
                                                            {team.team_name}
                                                        </TableCell>
                                                        <TableCell className="text-right text-lg font-semibold text-blue-600">
                                                            {team.subscriber_count}
                                                        </TableCell>
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    </CardContent>
                                </Card>
                            )}
                        </>
                    )}

                    {/* Assigned Teams */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center">
                                <Users className="mr-2 h-5 w-5" /> Assigned Teams
                            </CardTitle>
                            <CardDescription>Teams you are authorized to write for</CardDescription>
                        </CardHeader>
                        <CardContent>
                            {teams.length > 0 ? (
                                <div className="flex flex-wrap gap-2">
                                    {teams.map(assignment => (
                                        <Badge key={assignment.team_id} variant="secondary" className="text-sm py-1 px-3">
                                            {assignment.team_name}
                                        </Badge>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-gray-500">No teams assigned yet.</p>
                            )}
                        </CardContent>
                    </Card>

                    {/* Writeups */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between">
                            <div>
                                <CardTitle className="flex items-center">
                                    <FileText className="mr-2 h-5 w-5" /> Your Writeups
                                </CardTitle>
                                <CardDescription>Manage your commentaries and reports</CardDescription>
                            </div>
                            <Button onClick={() => navigate('/writer/writeup-editor')}>
                                <Plus className="mr-2 h-4 w-4" /> New Writeup
                            </Button>
                        </CardHeader>
                        <CardContent>
                            {commentaries.length > 0 ? (
                                <div className="space-y-4">
                                    {commentaries.map(item => (
                                        <div key={item.id} className="flex items-center justify-between p-4 border rounded-lg bg-white hover:bg-gray-50 transition-colors">
                                            <div>
                                                <h3 className="font-medium text-gray-900">{item.title || 'Untitled Writeup'}</h3>
                                                <div className="text-sm text-gray-500 flex gap-2 mt-1">
                                                    <Badge variant="outline" className="text-xs">{item.commentary_type}</Badge>
                                                    {item.team_name && <span className="text-gray-400">• {item.team_name}</span>}
                                                    <span className="text-gray-400">• {new Date(item.created_at).toLocaleDateString()}</span>
                                                    {item.is_premium && <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-200 border-amber-200">Premium</Badge>}
                                                </div>
                                            </div>
                                            <Button variant="ghost" size="sm" asChild>
                                                <Link to={`/writer/writeup-editor?id=${item.id}`}>Edit</Link>
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center py-8 text-gray-500">
                                    <p>No writeups found. Start by creating one!</p>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </main>
        </div>
    )
}
