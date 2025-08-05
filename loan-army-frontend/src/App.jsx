import { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button.jsx'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import { Textarea } from '@/components/ui/textarea.jsx'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select.jsx'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs.jsx'
import { Alert, AlertDescription } from '@/components/ui/alert.jsx'
import { 
  Users, 
  Mail, 
  Calendar, 
  Trophy, 
  TrendingUp, 
  Globe, 
  Star,
  ArrowRight,
  CheckCircle,
  AlertCircle,
  Home,
  UserPlus,
  FileText,
  Settings,
  BarChart3
} from 'lucide-react'
import './App.css'

// API configuration
const API_BASE_URL = '/api'

// API service
class APIService {
  static async request(endpoint, options = {}) {
    console.log(`🌐 Making API request to: ${API_BASE_URL}${endpoint}`, options)
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
      })
      
      console.log(`📡 Response status: ${response.status} ${response.statusText}`)
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error(`❌ HTTP error response body:`, errorText)
        throw new Error(`HTTP error! status: ${response.status}, body: ${errorText}`)
      }
      
      const data = await response.json()
      console.log(`✅ API response data:`, data)
      return data
    } catch (error) {
      console.error('❌ API request failed:', error)
      throw error
    }
  }

  static async getLeagues() {
    return this.request('/leagues')
  }

  static async getTeams(filters = {}) {
    console.log('🏟️ Getting teams with filters:', filters)
    const params = new URLSearchParams(filters)
    console.log('🔗 Teams URL params:', params.toString())
    return this.request(`/teams?${params}`)
  }

  static async getTeamLoans(teamId) {
    return this.request(`/teams/${teamId}/loans`)
  }

  static async getNewsletters(filters = {}) {
    const params = new URLSearchParams(filters)
    return this.request(`/newsletters?${params}`)
  }

  static async getSubscriptions(email) {
    return this.request(`/subscriptions?email=${encodeURIComponent(email)}`)
  }

  static async createSubscriptions(data) {
    return this.request('/subscriptions/bulk_create', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  static async getStats() {
    return this.request('/stats/overview')
  }

  static async initializeData() {
    return this.request('/init-data', {
      method: 'POST',
    })
  }

  static async debugDatabase() {
    console.log('🔍 Checking database debug info...')
    return this.request('/debug/database')
  }

  static async generateNewsletter(data) {
    console.log('📰 Generating newsletter for:', data)
    return this.request('/newsletters/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }
}

// League colors for visual identity
const LEAGUE_COLORS = {
  'Premier League': '#37003c',
  'La Liga': '#ff6b35',
  'Serie A': '#0066cc',
  'Bundesliga': '#d20515',
  'Ligue 1': '#dae025'
}

// Historical Newsletters page component
function HistoricalNewslettersPage() {
  const [teams, setTeams] = useState([])
  const [selectedTeams, setSelectedTeams] = useState([])
  const [selectedDate, setSelectedDate] = useState('')
  const [newsletters, setNewsletters] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    const loadTeams = async () => {
      try {
        console.log('🏟️ [Historical] Loading teams...')
        const data = await APIService.getTeams({ european_only: 'true' })
        console.log('✅ [Historical] Teams loaded:', data.length, 'teams')
        setTeams(data)
      } catch (error) {
        console.error('❌ [Historical] Failed to load teams:', error)
        setMessage({ type: 'error', text: 'Failed to load teams' })
      } finally {
        setLoading(false)
      }
    }

    loadTeams()
  }, [])

  const handleTeamToggle = (teamId) => {
    setSelectedTeams(prev => 
      prev.includes(teamId) 
        ? prev.filter(id => id !== teamId)
        : [...prev, teamId]
    )
  }

  const generateNewsletters = async () => {
    if (!selectedDate || selectedTeams.length === 0) {
      setMessage({ type: 'error', text: 'Please select a date and at least one team' })
      return
    }

    setGenerating(true)
    setNewsletters([])
    
    try {
      const generatedNewsletters = []
      
      // Generate newsletter for each selected team
      for (const teamId of selectedTeams) {
        console.log(`📰 Generating newsletter for team ${teamId} on ${selectedDate}`)
        
        try {
          const newsletter = await APIService.generateNewsletter({
            team_id: teamId,
            target_date: selectedDate,
            type: 'weekly'
          })
          
          generatedNewsletters.push({
            ...newsletter.newsletter,
            teamName: teams.find(t => t.id === teamId)?.name || 'Unknown Team'
          })
        } catch (error) {
          console.error(`❌ Failed to generate newsletter for team ${teamId}:`, error)
        }
      }
      
      setNewsletters(generatedNewsletters)
      setMessage({ 
        type: 'success', 
        text: `Generated ${generatedNewsletters.length} newsletters for ${selectedDate}` 
      })
      
    } catch (error) {
      console.error('❌ Failed to generate newsletters:', error)
      setMessage({ type: 'error', text: 'Failed to generate newsletters' })
    } finally {
      setGenerating(false)
    }
  }

  // Group teams by league
  const teamsByLeague = teams.reduce((acc, team) => {
    const league = team.league_name || 'Other'
    if (!acc[league]) acc[league] = []
    acc[league].push(team)
    return acc
  }, {})

  // Get date range for 2023-2024 season (available data)
  const minDate = '2023-08-01'
  const maxDate = '2024-06-30'

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">
            Historical Newsletters
          </h1>
          <p className="text-lg text-gray-600">
            Generate newsletters for the 2023-2024 season. Select teams and a date to see loan activities for that week.
          </p>
        </div>

        {message && (
          <div className={`mb-6 p-4 rounded-md ${
            message.type === 'error' 
              ? 'bg-red-50 border border-red-200 text-red-700' 
              : 'bg-green-50 border border-green-200 text-green-700'
          }`}>
            {message.text}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Selection Panel */}
          <div className="space-y-6">
            {/* Date Selection */}
            <Card>
              <CardHeader>
                <CardTitle>Select Date</CardTitle>
                <CardDescription>
                  Choose a date from the 2023-2024 season
                </CardDescription>
              </CardHeader>
              <CardContent>
                <input
                  type="date"
                  min={minDate}
                  max={maxDate}
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-sm text-gray-500 mt-2">
                  Season: August 1, 2023 - June 30, 2024
                </p>
              </CardContent>
            </Card>

            {/* Team Selection */}
            <Card>
              <CardHeader>
                <CardTitle>Select Teams</CardTitle>
                <CardDescription>
                  Choose teams to generate newsletters for ({selectedTeams.length} selected)
                </CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                  </div>
                ) : (
                  <div className="space-y-4 max-h-96 overflow-y-auto">
                    {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
                      <div key={league}>
                        <h3 className="text-sm font-semibold mb-2 flex items-center">
                          <div 
                            className="w-3 h-3 rounded mr-2"
                            style={{ backgroundColor: LEAGUE_COLORS[league] || '#666' }}
                          />
                          {league}
                        </h3>
                        <div className="grid grid-cols-1 gap-2 ml-5">
                          {leagueTeams.map((team) => (
                            <label key={team.id} className="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-2 rounded">
                              <input
                                type="checkbox"
                                checked={selectedTeams.includes(team.id)}
                                onChange={() => handleTeamToggle(team.id)}
                                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                              />
                              <span className="text-sm">{team.name}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Generate Button */}
            <Button 
              onClick={generateNewsletters}
              disabled={generating || !selectedDate || selectedTeams.length === 0}
              size="lg"
              className="w-full bg-blue-600 hover:bg-blue-700"
            >
              {generating ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Generating...
                </>
              ) : (
                <>
                  <Mail className="h-5 w-5 mr-2" />
                  Generate {selectedTeams.length} Newsletter{selectedTeams.length !== 1 ? 's' : ''}
                </>
              )}
            </Button>
          </div>

          {/* Generated Newsletters */}
          <div>
            <Card>
              <CardHeader>
                <CardTitle>Generated Newsletters</CardTitle>
                <CardDescription>
                  {newsletters.length > 0 
                    ? `${newsletters.length} newsletters for ${selectedDate}`
                    : 'Select teams and date to generate newsletters'
                  }
                </CardDescription>
              </CardHeader>
              <CardContent>
                {newsletters.length > 0 ? (
                  <div className="space-y-4 max-h-96 overflow-y-auto">
                    {newsletters.map((newsletter, index) => (
                      <div key={index} className="border rounded-lg p-4">
                        <h3 className="font-semibold text-lg mb-2">
                          {newsletter.teamName}
                        </h3>
                        <h4 className="font-medium text-gray-800 mb-2">
                          {newsletter.title}
                        </h4>
                        <div className="text-sm text-gray-600 whitespace-pre-wrap">
                          {typeof newsletter.content === 'string' 
                            ? JSON.parse(newsletter.content).summary || newsletter.content
                            : newsletter.content?.summary || 'No content available'
                          }
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12 text-gray-500">
                    <Mail className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>No newsletters generated yet</p>
                    <p className="text-sm">Select teams and a date above</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}

// Navigation component
function Navigation() {
  const location = useLocation()
  
  const navItems = [
    { path: '/', label: 'Home', icon: Home },
    { path: '/subscribe', label: 'Subscribe', icon: UserPlus },
    { path: '/teams', label: 'Browse Teams', icon: Users },
    { path: '/historical', label: 'Historical Newsletters', icon: Calendar },
    { path: '/newsletters', label: 'Newsletters', icon: FileText },
    { path: '/manage', label: 'Manage', icon: Settings },
    { path: '/stats', label: 'Statistics', icon: BarChart3 }
  ]

  return (
    <nav className="bg-white shadow-sm border-b">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link to="/" className="flex items-center space-x-2">
              <Trophy className="h-8 w-8 text-blue-600" />
              <span className="text-xl font-bold text-gray-900">Loan Army</span>
            </Link>
          </div>
          <div className="flex space-x-8">
            {navItems.map(({ path, label, icon: Icon }) => (
              <Link
                key={path}
                to={path}
                className={`inline-flex items-center px-1 pt-1 text-sm font-medium ${
                  location.pathname === path
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <Icon className="h-4 w-4 mr-1" />
                {label}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </nav>
  )
}

// Home page component
function HomePage() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await APIService.getStats()
        setStats(data)
      } catch (error) {
        console.error('Failed to load stats:', error)
      } finally {
        setLoading(false)
      }
    }

    loadStats()
  }, [])

  const handleInitializeData = async () => {
    try {
      await APIService.initializeData()
      // Reload stats after initialization
      const data = await APIService.getStats()
      setStats(data)
    } catch (error) {
      console.error('Failed to initialize data:', error)
    }
  }

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        {/* Hero Section */}
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Track European Football Loans
          </h1>
          <p className="text-xl text-gray-600 mb-8">
            Stay updated with AI-powered newsletters about your favorite teams' loaned players
          </p>
          <div className="flex justify-center space-x-4">
            <Link to="/subscribe">
              <Button size="lg" className="bg-blue-600 hover:bg-blue-700">
                <UserPlus className="h-5 w-5 mr-2" />
                Subscribe Now
              </Button>
            </Link>
            <Link to="/teams">
              <Button size="lg" variant="outline">
                <Users className="h-5 w-5 mr-2" />
                Browse Teams
              </Button>
            </Link>
          </div>
        </div>

        {/* Stats Cards */}
        {loading ? (
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading statistics...</p>
          </div>
        ) : stats ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">European Teams</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_teams}</div>
                <p className="text-xs text-muted-foreground">
                  From top 5 leagues
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Active Loans</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_active_loans}</div>
                <p className="text-xs text-muted-foreground">
                  Currently tracked
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Newsletters</CardTitle>
                <FileText className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_newsletters}</div>
                <p className="text-xs text-muted-foreground">
                  AI-generated reports
                </p>
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="text-center py-8">
            <Alert className="max-w-md mx-auto">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                No data available. Initialize sample data to get started.
              </AlertDescription>
            </Alert>
            <Button onClick={handleInitializeData} className="mt-4">
              Initialize Sample Data
            </Button>
          </div>
        )}

        {/* Features Section */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          <div className="text-center">
            <div className="bg-blue-100 rounded-full p-3 w-12 h-12 mx-auto mb-4">
              <Globe className="h-6 w-6 text-blue-600" />
            </div>
            <h3 className="text-lg font-semibold mb-2">European Focus</h3>
            <p className="text-gray-600">
              Track loans from Premier League, La Liga, Serie A, Bundesliga, and Ligue 1
            </p>
          </div>
          
          <div className="text-center">
            <div className="bg-green-100 rounded-full p-3 w-12 h-12 mx-auto mb-4">
              <Star className="h-6 w-6 text-green-600" />
            </div>
            <h3 className="text-lg font-semibold mb-2">AI-Powered</h3>
            <p className="text-gray-600">
              Get intelligent analysis and insights about player development
            </p>
          </div>
          
          <div className="text-center">
            <div className="bg-purple-100 rounded-full p-3 w-12 h-12 mx-auto mb-4">
              <Mail className="h-6 w-6 text-purple-600" />
            </div>
            <h3 className="text-lg font-semibold mb-2">Weekly Updates</h3>
            <p className="text-gray-600">
              Receive regular newsletters with the latest loan developments
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// Subscribe page component
function SubscribePage() {
  const [teams, setTeams] = useState([])
  const [selectedTeams, setSelectedTeams] = useState([])
  const [email, setEmail] = useState('')
  const [frequency, setFrequency] = useState('weekly')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    const loadTeams = async () => {
      try {
        // First check database status for debugging
        console.log('🔍 Checking database status first...')
        try {
          const dbStatus = await APIService.debugDatabase()
          console.log('📊 Database status:', dbStatus)
        } catch (dbError) {
          console.warn('⚠️ Could not get database status:', dbError)
        }

        console.log('🏟️ Loading teams...')
        const data = await APIService.getTeams({ european_only: 'true' })
        console.log('✅ Teams loaded successfully:', data.length, 'teams')
        setTeams(data)
      } catch (error) {
        console.error('❌ Failed to load teams:', error)
        setMessage({ type: 'error', text: 'Failed to load teams. Check console for details.' })
      } finally {
        setLoading(false)
      }
    }

    loadTeams()
  }, [])

  const handleTeamToggle = (teamId) => {
    setSelectedTeams(prev => 
      prev.includes(teamId) 
        ? prev.filter(id => id !== teamId)
        : [...prev, teamId]
    )
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (!email || selectedTeams.length === 0) {
      setMessage({ type: 'error', text: 'Please enter email and select at least one team' })
      return
    }

    setSubmitting(true)
    try {
      const result = await APIService.createSubscriptions({
        email,
        team_ids: selectedTeams,
        preferred_frequency: frequency
      })
      
      setMessage({ 
        type: 'success', 
        text: `Successfully subscribed to ${selectedTeams.length} teams!` 
      })
      setSelectedTeams([])
      setEmail('')
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to create subscriptions' })
    } finally {
      setSubmitting(false)
    }
  }

  // Group teams by league
  const teamsByLeague = teams.reduce((acc, team) => {
    const league = team.league_name || 'Other'
    if (!acc[league]) acc[league] = []
    acc[league].push(team)
    return acc
  }, {})

  return (
    <div className="max-w-4xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">
            Subscribe to Team Updates
          </h1>
          <p className="text-lg text-gray-600">
            Get AI-powered newsletters about your favorite teams' loaned players
          </p>
        </div>

        {message && (
          <Alert className={`mb-6 ${message.type === 'error' ? 'border-red-500' : 'border-green-500'}`}>
            {message.type === 'error' ? (
              <AlertCircle className="h-4 w-4" />
            ) : (
              <CheckCircle className="h-4 w-4" />
            )}
            <AlertDescription>{message.text}</AlertDescription>
          </Alert>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Subscription Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="email">Email Address</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your.email@example.com"
                  required
                />
              </div>
              
              <div>
                <Label htmlFor="frequency">Newsletter Frequency</Label>
                <Select value={frequency} onValueChange={setFrequency}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="weekly">Weekly</SelectItem>
                    <SelectItem value="monthly">Monthly</SelectItem>
                    <SelectItem value="both">Both Weekly & Monthly</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Select Teams</CardTitle>
              <CardDescription>
                Choose the teams you want to follow ({selectedTeams.length} selected)
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="text-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                </div>
              ) : (
                <div className="space-y-6">
                  {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
                    <div key={league}>
                      <h3 className="text-lg font-semibold mb-3 flex items-center">
                        <div 
                          className="w-4 h-4 rounded mr-2"
                          style={{ backgroundColor: LEAGUE_COLORS[league] || '#666' }}
                        />
                        {league}
                      </h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {leagueTeams.map((team) => (
                          <div
                            key={team.id}
                            className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                              selectedTeams.includes(team.id)
                                ? 'border-blue-500 bg-blue-50'
                                : 'border-gray-200 hover:border-gray-300'
                            }`}
                            onClick={() => handleTeamToggle(team.id)}
                          >
                            <div className="flex items-center justify-between">
                              <div>
                                <div className="font-medium">{team.name}</div>
                                <div className="text-sm text-gray-500">
                                  {team.current_loaned_out_count} active loans
                                </div>
                              </div>
                              {selectedTeams.includes(team.id) && (
                                <CheckCircle className="h-5 w-5 text-blue-600" />
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex justify-center">
            <Button 
              type="submit" 
              size="lg" 
              disabled={submitting || selectedTeams.length === 0}
              className="bg-blue-600 hover:bg-blue-700"
            >
              {submitting ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Subscribing...
                </>
              ) : (
                <>
                  <Mail className="h-5 w-5 mr-2" />
                  Subscribe to {selectedTeams.length} Teams
                </>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

// Teams page component
function TeamsPage() {
  const [teams, setTeams] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    const loadTeams = async () => {
      try {
        // Check database status for debugging
        console.log('🔍 [TeamsPage] Checking database status...')
        try {
          const dbStatus = await APIService.debugDatabase()
          console.log('📊 [TeamsPage] Database status:', dbStatus)
        } catch (dbError) {
          console.warn('⚠️ [TeamsPage] Could not get database status:', dbError)
        }

        const filters = { european_only: 'true' }
        if (filter === 'with_loans') {
          filters.has_loans = 'true'
        }
        
        console.log('🏟️ [TeamsPage] Loading teams with filters:', filters)
        const data = await APIService.getTeams(filters)
        console.log('✅ [TeamsPage] Teams loaded successfully:', data.length, 'teams')
        setTeams(data)
      } catch (error) {
        console.error('❌ [TeamsPage] Failed to load teams:', error)
      } finally {
        setLoading(false)
      }
    }

    loadTeams()
  }, [filter])

  // Group teams by league
  const teamsByLeague = teams.reduce((acc, team) => {
    const league = team.league_name || 'Other'
    if (!acc[league]) acc[league] = []
    acc[league].push(team)
    return acc
  }, {})

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              European Teams
            </h1>
            <p className="text-lg text-gray-600">
              Browse teams from Europe's top 5 leagues
            </p>
          </div>
          
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Teams</SelectItem>
              <SelectItem value="with_loans">Teams with Loans</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading teams...</p>
          </div>
        ) : (
          <div className="space-y-8">
            {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
              <div key={league}>
                <h2 className="text-2xl font-bold mb-4 flex items-center">
                  <div 
                    className="w-6 h-6 rounded mr-3"
                    style={{ backgroundColor: LEAGUE_COLORS[league] || '#666' }}
                  />
                  {league}
                  <Badge variant="secondary" className="ml-2">
                    {leagueTeams.length} teams
                  </Badge>
                </h2>
                
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {leagueTeams.map((team) => (
                    <Card key={team.id} className="hover:shadow-lg transition-shadow">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-lg">{team.name}</CardTitle>
                        <CardDescription>
                          {team.country} • Founded {team.founded || 'N/A'}
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <div className="flex justify-between items-center">
                          <div className="text-sm text-gray-600">
                            <div className="flex items-center">
                              <TrendingUp className="h-4 w-4 mr-1" />
                              {team.current_loaned_out_count} active loans
                            </div>
                          </div>
                          <Link to={`/teams/${team.id}`}>
                            <Button size="sm" variant="outline">
                              View Details
                              <ArrowRight className="h-4 w-4 ml-1" />
                            </Button>
                          </Link>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// Newsletters page component
function NewslettersPage() {
  const [newsletters, setNewsletters] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadNewsletters = async () => {
      try {
        const data = await APIService.getNewsletters({ published_only: 'true' })
        setNewsletters(data)
      } catch (error) {
        console.error('Failed to load newsletters:', error)
      } finally {
        setLoading(false)
      }
    }

    loadNewsletters()
  }, [])

  return (
    <div className="max-w-4xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">
            Published Newsletters
          </h1>
          <p className="text-lg text-gray-600">
            AI-generated insights about European team loan activities
          </p>
        </div>

        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading newsletters...</p>
          </div>
        ) : newsletters.length === 0 ? (
          <div className="text-center py-12">
            <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No newsletters yet</h3>
            <p className="text-gray-600">
              Newsletters will appear here once they are generated and published.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {newsletters.map((newsletter) => (
              <Card key={newsletter.id}>
                <CardHeader>
                  <div className="flex justify-between items-start">
                    <div>
                      <CardTitle className="text-xl">{newsletter.title}</CardTitle>
                      <CardDescription className="mt-1">
                        {newsletter.team_name} • {newsletter.newsletter_type} newsletter
                      </CardDescription>
                    </div>
                    <Badge variant="secondary">
                      {new Date(newsletter.published_date).toLocaleDateString()}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="prose max-w-none">
                    {newsletter.content.substring(0, 300)}...
                  </div>
                  <div className="mt-4 flex justify-between items-center">
                    <div className="text-sm text-gray-500">
                      <Calendar className="h-4 w-4 inline mr-1" />
                      {newsletter.week_start_date && newsletter.week_end_date && (
                        `${new Date(newsletter.week_start_date).toLocaleDateString()} - ${new Date(newsletter.week_end_date).toLocaleDateString()}`
                      )}
                    </div>
                    <Button variant="outline" size="sm">
                      Read Full Newsletter
                      <ArrowRight className="h-4 w-4 ml-1" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// Manage subscriptions page
function ManagePage() {
  const [email, setEmail] = useState('')
  const [subscriptions, setSubscriptions] = useState([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)

  const handleSearch = async (e) => {
    e.preventDefault()
    
    if (!email) {
      setMessage({ type: 'error', text: 'Please enter your email address' })
      return
    }

    setLoading(true)
    try {
      const data = await APIService.getSubscriptions(email)
      setSubscriptions(data)
      
      if (data.length === 0) {
        setMessage({ type: 'info', text: 'No subscriptions found for this email address' })
      } else {
        setMessage(null)
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to load subscriptions' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">
            Manage Subscriptions
          </h1>
          <p className="text-lg text-gray-600">
            View and manage your newsletter subscriptions
          </p>
        </div>

        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Find Your Subscriptions</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSearch} className="flex space-x-4">
              <div className="flex-1">
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your email address"
                  required
                />
              </div>
              <Button type="submit" disabled={loading}>
                {loading ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Searching...
                  </>
                ) : (
                  'Search'
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        {message && (
          <Alert className={`mb-6 ${message.type === 'error' ? 'border-red-500' : message.type === 'info' ? 'border-blue-500' : 'border-green-500'}`}>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{message.text}</AlertDescription>
          </Alert>
        )}

        {subscriptions.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Your Subscriptions</h2>
            {subscriptions.map((subscription) => (
              <Card key={subscription.id}>
                <CardContent className="pt-6">
                  <div className="flex justify-between items-center">
                    <div>
                      <h3 className="font-semibold">{subscription.team?.name}</h3>
                      <p className="text-sm text-gray-600">
                        {subscription.preferred_frequency} newsletters
                      </p>
                      <p className="text-xs text-gray-500">
                        Subscribed on {new Date(subscription.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Badge variant={subscription.active ? "default" : "secondary"}>
                        {subscription.active ? "Active" : "Inactive"}
                      </Badge>
                      {subscription.active && (
                        <Button variant="outline" size="sm">
                          Unsubscribe
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// Statistics page
function StatsPage() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await APIService.getStats()
        setStats(data)
      } catch (error) {
        console.error('Failed to load stats:', error)
      } finally {
        setLoading(false)
      }
    }

    loadStats()
  }, [])

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">
            System Statistics
          </h1>
          <p className="text-lg text-gray-600">
            Overview of the Loan Army platform
          </p>
        </div>

        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading statistics...</p>
          </div>
        ) : stats ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Teams</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_teams}</div>
                <p className="text-xs text-muted-foreground">
                  European teams tracked
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Teams with Loans</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.teams_with_loans}</div>
                <p className="text-xs text-muted-foreground">
                  Have active loans
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Active Loans</CardTitle>
                <Globe className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_active_loans}</div>
                <p className="text-xs text-muted-foreground">
                  Currently tracked
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Published Newsletters</CardTitle>
                <FileText className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_newsletters}</div>
                <p className="text-xs text-muted-foreground">
                  AI-generated reports
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Active Subscriptions</CardTitle>
                <Mail className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_subscriptions}</div>
                <p className="text-xs text-muted-foreground">
                  Newsletter subscribers
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">European Leagues</CardTitle>
                <Trophy className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.european_leagues}</div>
                <p className="text-xs text-muted-foreground">
                  Top leagues covered
                </p>
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="text-center py-12">
            <Alert className="max-w-md mx-auto">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                Failed to load statistics. Please try again later.
              </AlertDescription>
            </Alert>
          </div>
        )}
      </div>
    </div>
  )
}

// Main App component
function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-50">
        <Navigation />
        <main>
                  <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/subscribe" element={<SubscribePage />} />
          <Route path="/teams" element={<TeamsPage />} />
          <Route path="/historical" element={<HistoricalNewslettersPage />} />
          <Route path="/newsletters" element={<NewslettersPage />} />
          <Route path="/manage" element={<ManagePage />} />
          <Route path="/stats" element={<StatsPage />} />
        </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App

