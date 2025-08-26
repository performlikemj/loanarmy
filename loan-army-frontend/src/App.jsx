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

// Universal Date Picker Component
function UniversalDatePicker({ onDateChange, className = "" }) {
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [isCustomRange, setIsCustomRange] = useState(false)

  const handlePresetChange = (preset) => {
    const today = new Date()
    let start, end

    switch (preset) {
      case 'today':
        start = end = today.toISOString().split('T')[0]
        break
      case 'this_week':
        const monday = new Date(today)
        monday.setDate(today.getDate() - today.getDay() + 1)
        start = monday.toISOString().split('T')[0]
        end = new Date(monday.getTime() + 6 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
        break
      case 'this_month':
        start = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0]
        end = new Date(today.getFullYear(), today.getMonth() + 1, 0).toISOString().split('T')[0]
        break
      case 'last_30_days':
        start = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
        end = today.toISOString().split('T')[0]
        break
      case 'last_90_days':
        start = new Date(today.getTime() - 90 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
        end = today.toISOString().split('T')[0]
        break
      case 'last_year':
        start = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate()).toISOString().split('T')[0]
        end = today.toISOString().split('T')[0]
        break
      case 'all_time':
        start = '2020-01-01' // Reasonable start date for football data
        end = today.toISOString().split('T')[0]
        break
      case 'custom':
        setIsCustomRange(true)
        return
      default:
        return
    }

    setStartDate(start)
    setEndDate(end)
    setIsCustomRange(false)
    onDateChange({ startDate: start, endDate: end, preset })
  }

  const handleCustomDateChange = () => {
    if (startDate && endDate) {
      onDateChange({ startDate, endDate, preset: 'custom' })
    }
  }

  useEffect(() => {
    // Set default to last 30 days
    handlePresetChange('last_30_days')
  }, [])

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="flex flex-wrap gap-2">
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => handlePresetChange('today')}
        >
          Today
        </Button>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => handlePresetChange('this_week')}
        >
          This Week
        </Button>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => handlePresetChange('this_month')}
        >
          This Month
        </Button>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => handlePresetChange('last_30_days')}
        >
          Last 30 Days
        </Button>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => handlePresetChange('last_90_days')}
        >
          Last 90 Days
        </Button>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => handlePresetChange('last_year')}
        >
          Last Year
        </Button>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => handlePresetChange('all_time')}
        >
          All Time
        </Button>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => handlePresetChange('custom')}
        >
          Custom Range
        </Button>
      </div>

      {isCustomRange && (
        <div className="flex items-center space-x-4 p-4 border rounded-lg bg-gray-50">
          <div className="flex items-center space-x-2">
            <Label htmlFor="start-date">Start Date:</Label>
            <Input
              id="start-date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-40"
            />
          </div>
          <div className="flex items-center space-x-2">
            <Label htmlFor="end-date">End Date:</Label>
            <Input
              id="end-date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-40"
            />
          </div>
          <Button 
            size="sm" 
            onClick={handleCustomDateChange}
            disabled={!startDate || !endDate}
          >
            Apply
          </Button>
        </div>
      )}

      {(startDate && endDate) && (
        <div className="text-sm text-gray-600 bg-blue-50 p-2 rounded">
          Showing data from <strong>{new Date(startDate).toLocaleDateString()}</strong> to <strong>{new Date(endDate).toLocaleDateString()}</strong>
        </div>
      )}
    </div>
  )
}

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

  static async createSubscriptions(data) {
    return this.request('/subscriptions/bulk_create', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  static async getManageState(token) {
    return this.request(`/subscriptions/manage/${encodeURIComponent(token)}`)
  }

  static async updateManageState(token, data) {
    return this.request(`/subscriptions/manage/${encodeURIComponent(token)}`, {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  static async tokenUnsubscribe(token) {
    return this.request(`/subscriptions/unsubscribe/${encodeURIComponent(token)}`, {
      method: 'POST',
    })
  }

  static async verifyToken(token) {
    return this.request(`/verify/${encodeURIComponent(token)}`, {
      method: 'POST',
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



  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">
            Historical Newsletters
          </h1>
          <p className="text-lg text-gray-600">
            Generate newsletters for any date. Select teams and a date to see loan activities for that week.
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
                  Choose any date to generate newsletters for that week
                </CardDescription>
              </CardHeader>
              <CardContent>
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-sm text-gray-500 mt-2">
                  Select any date to generate newsletters for that week
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
    { path: '/newsletters', label: 'Newsletters', icon: FileText }
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
        team_ids: selectedTeams
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
  const [expandedTeamId, setExpandedTeamId] = useState(null)
  const [teamLoans, setTeamLoans] = useState({})
  const [flagState, setFlagState] = useState({ open: false, team: null, loan: null, reason: '', email: '' })
  const [submittingFlag, setSubmittingFlag] = useState(false)
  const [teamEmail, setTeamEmail] = useState({})
  const [subscribingTeamId, setSubscribingTeamId] = useState(null)

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

  const toggleExpand = async (teamId) => {
    setExpandedTeamId(prev => (prev === teamId ? null : teamId))
    if (!teamLoans[teamId]) {
      try {
        const loans = await APIService.getTeamLoans(teamId)
        setTeamLoans(prev => ({ ...prev, [teamId]: loans }))
      } catch (e) {
        console.error('❌ Failed to load loans for team', teamId, e)
      }
    }
  }

  const openFlag = (team, loan) => {
    setFlagState({ open: true, team, loan, reason: '', email: '' })
  }
  const closeFlag = () => setFlagState(prev => ({ ...prev, open: false }))
  const submitFlag = async () => {
    if (!flagState.reason.trim()) return
    setSubmittingFlag(true)
    try {
      const now = new Date()
      const season = now.getMonth() >= 7 ? now.getFullYear() : now.getFullYear() - 1
      await fetch('/api/loans/flags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_id: flagState.loan?.player_id,
          primary_team_api_id: flagState.team?.team_id,
          loan_team_api_id: flagState.loan?.loan_team_api_id,
          season,
          reason: flagState.reason,
          email: flagState.email || undefined,
        })
      })
      alert('Thanks for the report. We will review it.')
      closeFlag()
    } catch (e) {
      console.error('Flag submit failed', e)
      alert('Failed to submit flag. Please try again later.')
    } finally {
      setSubmittingFlag(false)
    }
  }
  const handleEmailChange = (teamId, val) => setTeamEmail(prev => ({ ...prev, [teamId]: val }))
  const subscribeTeam = async (team) => {
    const email = (teamEmail[team.id] || '').trim()
    if (!email) { alert('Please enter your email'); return }
    setSubscribingTeamId(team.id)
    try {
      await fetch('/api/subscriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, team_id: team.id, preferred_frequency: 'weekly' })
      })
      alert('Subscribed successfully')
    } catch (e) {
      console.error('Subscribe failed', e)
      alert('Subscription failed. Please try again later.')
    } finally {
      setSubscribingTeamId(null)
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
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              European Teams
            </h1>
            <div className="flex items-center space-x-2 mb-2">
              <Badge variant="secondary" className="bg-green-100 text-green-800 border-green-300">
                <Calendar className="h-3 w-3 mr-1" />
                Current Season
              </Badge>
            </div>
            <p className="text-lg text-gray-600">
              Browse current season teams from Europe's top 5 leagues
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

        {/* Current Season Indicator */}
        <Card className="mb-6 bg-blue-50 border-blue-200">
          <CardContent className="pt-6">
            <div className="flex items-center space-x-3">
              <Calendar className="h-5 w-5 text-blue-600" />
              <div>
                <h3 className="text-sm font-medium text-blue-900">
                  Current Season Teams
                </h3>
                <p className="text-sm text-blue-700">
                  Showing top-flight teams from Europe's major leagues for the current season. Team data and loan information reflects the latest available season.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

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
                        <div className="flex items-center gap-2 mb-3">
                          <input
                            type="email"
                            value={teamEmail[team.id] || ''}
                            onChange={(e) => handleEmailChange(team.id, e.target.value)}
                            placeholder="you@example.com"
                            className="border rounded px-2 py-1 text-sm w-full"
                          />
                          <Button size="sm" onClick={() => subscribeTeam(team)} disabled={subscribingTeamId === team.id}>
                            {subscribingTeamId === team.id ? 'Subscribing...' : 'Subscribe'}
                          </Button>
                        </div>
                        <div className="flex justify-between items-center">
                          <div className="text-sm text-gray-600">
                            <div className="flex items-center">
                              <TrendingUp className="h-4 w-4 mr-1" />
                              {team.current_loaned_out_count} active loans
                            </div>
                          </div>
                          <Button size="sm" variant="outline" onClick={() => toggleExpand(team.id)}>
                            {expandedTeamId === team.id ? 'Hide Loans' : 'Show Loans'}
                            <ArrowRight className="h-4 w-4 ml-1" />
                          </Button>
                        </div>
                        {expandedTeamId === team.id && (
                          <div className="mt-4 space-y-2">
                            {(teamLoans[team.id] || []).length === 0 ? (
                              <div className="text-sm text-gray-500">No loans found.</div>
                            ) : (
                              (teamLoans[team.id] || []).map((loan) => (
                                <div key={loan.id} className="border rounded p-2 text-sm">
                                  <div className="font-medium">{loan.player_name}</div>
                                  <div className="text-gray-600">Loan at {loan.loan_team_name}</div>
                                  <div className="text-gray-500">Apps: {loan.appearances} • Goals: {loan.goals} • Assists: {loan.assists}</div>
                                  <div className="mt-2">
                                    <Button size="xs" variant="outline" onClick={() => openFlag(team, loan)}>Flag incorrect</Button>
                                  </div>
                                  {flagState.open && flagState.team?.id === team.id && flagState.loan?.id === loan.id && (
                                    <div className="mt-2 border-t pt-2">
                                      <textarea
                                        className="w-full border rounded p-2 text-sm"
                                        rows="3"
                                        placeholder="Why is this incorrect?"
                                        value={flagState.reason}
                                        onChange={(e) => setFlagState(prev => ({ ...prev, reason: e.target.value }))}
                                      />
                                      <input
                                        type="email"
                                        className="w-full border rounded p-2 text-sm mt-2"
                                        placeholder="Optional email"
                                        value={flagState.email}
                                        onChange={(e) => setFlagState(prev => ({ ...prev, email: e.target.value }))}
                                      />
                                      <div className="mt-2 flex gap-2">
                                        <Button size="sm" onClick={submitFlag} disabled={submittingFlag || !flagState.reason.trim()}>
                                          {submittingFlag ? 'Submitting...' : 'Submit flag'}
                                        </Button>
                                        <Button size="sm" variant="outline" onClick={closeFlag}>Cancel</Button>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              ))
                            )}
                          </div>
                        )}
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
  const [dateRange, setDateRange] = useState({ startDate: '', endDate: '', preset: 'all_time' })
  const [expandedId, setExpandedId] = useState(null)

  useEffect(() => {
    const loadNewsletters = async () => {
      try {
        const params = { published_only: 'true' }
        
        // Use date range if available, otherwise show all newsletters
        if (dateRange.startDate && dateRange.endDate) {
          params.week_start = dateRange.startDate
          params.week_end = dateRange.endDate
        }
        
        const data = await APIService.getNewsletters(params)
        setNewsletters(data)
      } catch (error) {
        console.error('Failed to load newsletters:', error)
      } finally {
        setLoading(false)
      }
    }

    loadNewsletters()
  }, [dateRange])



  return (
    <div className="max-w-4xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">
            Published Newsletters
          </h1>
          <p className="text-lg text-gray-600">
            Insights about European team loan activities
          </p>
        </div>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Filter by Date Range</CardTitle>
            <CardDescription>Select a date range to view newsletters from that period</CardDescription>
          </CardHeader>
          <CardContent>
            <UniversalDatePicker onDateChange={setDateRange} />
          </CardContent>
        </Card>

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
                    <div className="flex items-center space-x-2">
                      <Badge variant="secondary">
                        {new Date(newsletter.published_date).toLocaleDateString()}
                      </Badge>
                      <Button size="sm" variant="outline" onClick={() => setExpandedId(expandedId === newsletter.id ? null : newsletter.id)}>
                        {expandedId === newsletter.id ? 'Hide' : 'Read'}
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="text-sm text-gray-500 mb-2">
                    <Calendar className="h-4 w-4 inline mr-1" />
                    {newsletter.week_start_date && newsletter.week_end_date && (
                      `${new Date(newsletter.week_start_date).toLocaleDateString()} - ${new Date(newsletter.week_end_date).toLocaleDateString()}`
                    )}
                  </div>
                  {expandedId === newsletter.id ? (
                    <div className="max-w-none">
                      {newsletter.rendered?.web_html ? (
                        <div dangerouslySetInnerHTML={{ __html: newsletter.rendered.web_html }} className="prose max-w-none" />
                      ) : (
                        (() => {
                          try {
                            const obj = JSON.parse(newsletter.content)
                            return (
                              <div className="space-y-6">
                                {/* Newsletter Header */}
                                <div className="bg-gradient-to-r from-blue-50 to-gray-50 p-6 rounded-lg border-l-4 border-blue-500">
                                  <h2 className="text-2xl font-bold text-gray-900 mb-3">{obj.title || newsletter.title}</h2>
                                  {obj.range && (
                                    <div className="text-sm text-gray-600 mb-3">
                                      📅 Week: {obj.range[0]} - {obj.range[1]}
                                    </div>
                                  )}
                                  {obj.summary && (
                                    <div className="text-gray-700 leading-relaxed text-lg">
                                      {obj.summary}
                                    </div>
                                  )}
                                </div>

                                {/* Key Highlights Section */}
                                {obj.highlights && Array.isArray(obj.highlights) && obj.highlights.length > 0 && (
                                  <div className="bg-yellow-50 p-5 rounded-lg border-l-4 border-yellow-400">
                                    <h3 className="text-lg font-bold text-gray-900 mb-3 flex items-center">
                                      ⭐ Key Highlights
                                    </h3>
                                    <ul className="space-y-2">
                                      {obj.highlights.map((highlight, idx) => (
                                        <li key={idx} className="flex items-start">
                                          <span className="bg-yellow-400 text-yellow-900 rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold mr-3 mt-0.5 flex-shrink-0">
                                            {idx + 1}
                                          </span>
                                          <span className="text-gray-700">{highlight}</span>
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                {/* Performance Stats */}
                                {obj.by_numbers && (
                                  <div className="bg-gray-50 p-5 rounded-lg">
                                    <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center">
                                      📊 By The Numbers
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                      {obj.by_numbers.minutes_leaders && obj.by_numbers.minutes_leaders.length > 0 && (
                                        <div className="bg-white p-4 rounded-lg shadow-sm border">
                                          <h4 className="font-semibold text-gray-900 mb-3 flex items-center">
                                            ⏱️ Minutes Leaders
                                          </h4>
                                          <div className="space-y-2">
                                            {obj.by_numbers.minutes_leaders.map((player, idx) => (
                                              <div key={idx} className="flex justify-between items-center">
                                                <span className="font-medium text-gray-700">{player.player}</span>
                                                <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-sm font-bold">
                                                  {player.minutes}'
                                                </span>
                                              </div>
                                            ))}
                                          </div>
                                        </div>
                                      )}
                                      
                                      {obj.by_numbers.ga_leaders && obj.by_numbers.ga_leaders.length > 0 && (
                                        <div className="bg-white p-4 rounded-lg shadow-sm border">
                                          <h4 className="font-semibold text-gray-900 mb-3 flex items-center">
                                            ⚽ Goal Contributors
                                          </h4>
                                          <div className="space-y-2">
                                            {obj.by_numbers.ga_leaders.map((player, idx) => (
                                              <div key={idx} className="flex justify-between items-center">
                                                <span className="font-medium text-gray-700">{player.player}</span>
                                                <div className="flex space-x-1">
                                                  <span className="bg-green-100 text-green-800 px-2 py-1 rounded text-sm font-bold">
                                                    {player.g}G
                                                  </span>
                                                  <span className="bg-purple-100 text-purple-800 px-2 py-1 rounded text-sm font-bold">
                                                    {player.a}A
                                                  </span>
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                )}

                                {/* Detailed Sections */}
                                {obj.sections && obj.sections.length > 0 && (
                                  <div className="space-y-4">
                                    <h3 className="text-lg font-bold text-gray-900 flex items-center">
                                      📋 Detailed Report
                                    </h3>
                                    {obj.sections.map((sec, idx) => (
                                      <div key={idx} className="bg-white border rounded-lg overflow-hidden shadow-sm">
                                        {sec.title && (
                                          <div className="bg-gray-100 px-5 py-3 border-b">
                                            <h4 className="font-semibold text-gray-900">{sec.title}</h4>
                                          </div>
                                        )}
                                        <div className="p-5">
                                          {sec.content && (
                                            <div className="text-gray-700 mb-4">{sec.content}</div>
                                          )}
                                          {sec.items && Array.isArray(sec.items) && (
                                            <div className="space-y-4">
                                              {sec.items.map((it, j) => (
                                                <div key={j} className="border-l-4 border-blue-200 pl-4 py-2">
                                                  <div className="flex flex-wrap items-center gap-2 mb-2">
                                                    {it.player_name && (
                                                      <span className="font-semibold text-lg text-gray-900">
                                                        {it.player_name}
                                                      </span>
                                                    )}
                                                    {it.loan_team && (
                                                      <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-sm font-medium">
                                                        → {it.loan_team}
                                                      </span>
                                                    )}
                                                    {it.stats && (
                                                      <div className="flex gap-1">
                                                        {it.stats.goals > 0 && (
                                                          <span className="bg-green-100 text-green-800 px-2 py-1 rounded text-xs">
                                                            {it.stats.goals}G
                                                          </span>
                                                        )}
                                                        {it.stats.assists > 0 && (
                                                          <span className="bg-purple-100 text-purple-800 px-2 py-1 rounded text-xs">
                                                            {it.stats.assists}A
                                                          </span>
                                                        )}
                                                        {it.stats.minutes > 0 && (
                                                          <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">
                                                            {it.stats.minutes}'
                                                          </span>
                                                        )}
                                                      </div>
                                                    )}
                                                  </div>
                                                  {it.week_summary && (
                                                    <p className="text-gray-700 leading-relaxed">{it.week_summary}</p>
                                                  )}
                                                </div>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                )}

                                {/* Fan Pulse Section */}
                                {obj.fan_pulse && Array.isArray(obj.fan_pulse) && obj.fan_pulse.length > 0 && (
                                  <div className="bg-purple-50 p-5 rounded-lg border-l-4 border-purple-400">
                                    <h3 className="text-lg font-bold text-gray-900 mb-3 flex items-center">
                                      💬 Fan Pulse
                                    </h3>
                                    <div className="space-y-3">
                                      {obj.fan_pulse.map((pulse, idx) => (
                                        <div key={idx} className="bg-white p-3 rounded border-l-2 border-purple-200">
                                          <p className="text-gray-700 italic">"{pulse}"</p>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )
                          } catch {
                            return (
                              <div className="prose max-w-none">
                                <div className="bg-gray-50 p-4 rounded-lg">
                                  <h3 className="text-lg font-medium text-gray-900 mb-2">Newsletter Content</h3>
                                  <div className="whitespace-pre-wrap text-gray-700">{newsletter.content}</div>
                                </div>
                              </div>
                            )
                          }
                        })()
                      )}
                    </div>
                  ) : (
                    <div className="prose max-w-none">
                      {(() => {
                        try {
                          const obj = JSON.parse(newsletter.content)
                          return (
                            <div className="space-y-3">
                              {/* Summary */}
                              {obj.summary && (
                                <div className="text-gray-700 leading-relaxed">
                                  {obj.summary}
                                </div>
                              )}
                              
                              {/* Key Highlights */}
                              {obj.highlights && Array.isArray(obj.highlights) && obj.highlights.length > 0 && (
                                <div>
                                  <div className="text-sm font-semibold text-gray-900 mb-2">Key Highlights:</div>
                                  <ul className="list-disc ml-5 space-y-1">
                                    {obj.highlights.slice(0, 3).map((highlight, idx) => (
                                      <li key={idx} className="text-sm text-gray-700">{highlight}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              
                              {/* Top Performers */}
                              {obj.by_numbers && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
                                  {obj.by_numbers.minutes_leaders && obj.by_numbers.minutes_leaders.length > 0 && (
                                    <div className="bg-gray-50 p-3 rounded-lg">
                                      <div className="text-sm font-semibold text-gray-900 mb-2">Minutes Leaders:</div>
                                      <div className="space-y-1">
                                        {obj.by_numbers.minutes_leaders.slice(0, 2).map((player, idx) => (
                                          <div key={idx} className="text-sm text-gray-700">
                                            <span className="font-medium">{player.player}</span>: {player.minutes}'
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                  
                                  {obj.by_numbers.ga_leaders && obj.by_numbers.ga_leaders.length > 0 && (
                                    <div className="bg-gray-50 p-3 rounded-lg">
                                      <div className="text-sm font-semibold text-gray-900 mb-2">Goal Contributors:</div>
                                      <div className="space-y-1">
                                        {obj.by_numbers.ga_leaders.slice(0, 2).map((player, idx) => (
                                          <div key={idx} className="text-sm text-gray-700">
                                            <span className="font-medium">{player.player}</span>: {player.g}G {player.a}A
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}
                              
                              {/* Preview of sections */}
                              {obj.sections && obj.sections.length > 0 && (
                                <div className="mt-3">
                                  <div className="text-sm font-semibold text-gray-900 mb-2">This Week's Activity:</div>
                                  <div className="space-y-2">
                                    {obj.sections.slice(0, 2).map((section, idx) => (
                                      <div key={idx} className="border-l-2 border-blue-200 pl-3">
                                        <div className="text-sm font-medium text-gray-800">{section.title}</div>
                                        {section.items && section.items.length > 0 && (
                                          <div className="text-sm text-gray-600 mt-1">
                                            {section.items.length} player{section.items.length !== 1 ? 's' : ''} featured
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                              
                              {/* Read More indicator */}
                              <div className="mt-4 pt-3 border-t border-gray-200">
                                <div className="text-sm text-blue-600 font-medium">
                                  Click "Read" to see the complete newsletter
                                </div>
                              </div>
                            </div>
                          )
                        } catch {
                          // Fallback to showing content summary if JSON parsing fails
                          const content = newsletter.content || newsletter.structured_content || ''
                          if (content.length > 200) {
                            return (
                              <div className="space-y-3">
                                <div className="text-gray-700 leading-relaxed">
                                  {content.substring(0, 200)}...
                                </div>
                                <div className="pt-3 border-t border-gray-200">
                                  <div className="text-sm text-blue-600 font-medium">
                                    Click "Read" to see the complete newsletter
                                  </div>
                                </div>
                              </div>
                            )
                          }
                          return (
                            <div className="space-y-3">
                              <div className="text-gray-700 leading-relaxed">
                                {content}
                              </div>
                              <div className="pt-3 border-t border-gray-200">
                                <div className="text-sm text-blue-600 font-medium">
                                  Click "Read" to see the complete newsletter
                                </div>
                              </div>
                            </div>
                          )
                        }
                      })()}
                    </div>
                  )}
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
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [subs, setSubs] = useState([])
  const [message, setMessage] = useState(null)

  const token = new URLSearchParams(window.location.search).get('token')

  useEffect(() => {
    const load = async () => {
      if (!token) {
        setStatus('error')
        setMessage({ type: 'error', text: 'Missing token' })
        return
      }
      try {
        const data = await APIService.getManageState(token)
        setSubs(data.subscriptions || [])
        setStatus('ready')
      } catch (e) {
        setStatus('error')
        setMessage({ type: 'error', text: 'Invalid or expired link. Request a new manage link from your email.' })
      }
    }
    load()
  }, [token])

  const toggleTeam = (teamId) => {
    setSubs((prev) => {
      const exists = prev.some((s) => s.team_id === teamId)
      if (exists) {
        return prev.filter((s) => s.team_id !== teamId)
      }
      return [...prev, { team_id: teamId }]
    })
  }

  const save = async () => {
    try {
      const teamIds = subs.map((s) => s.team_id)
      await APIService.updateManageState(token, { team_ids: teamIds })
      setMessage({ type: 'success', text: 'Preferences updated.' })
    } catch (e) {
      setMessage({ type: 'error', text: 'Failed to update preferences.' })
    }
  }

  return (
    <div className="max-w-4xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">Manage Subscriptions</h1>
          <p className="text-lg text-gray-600">Use the secure link from your email to manage preferences.</p>
        </div>

        {message && (
          <Alert className={`mb-6 ${message.type === 'error' ? 'border-red-500' : 'border-green-500'}`}>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{message.text}</AlertDescription>
          </Alert>
        )}

        {status === 'loading' && (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading…</p>
          </div>
        )}

        {status === 'ready' && (
          <Card>
            <CardHeader>
              <CardTitle>Update Preferences</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Subscribed Teams</Label>
                <p className="text-sm text-gray-500 mb-2">Toggle teams to stay subscribed. (Team list display simplified.)</p>
                <div className="grid grid-cols-1 gap-2">
                  {subs.map((s) => (
                    <div key={s.team_id} className="flex items-center justify-between border rounded p-2">
                      <span className="text-sm">Team #{s.team_id}</span>
                      <Button size="sm" variant="outline" onClick={() => toggleTeam(s.team_id)}>Remove</Button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-end">
                <Button onClick={save}>
                  Save Changes
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {status === 'error' && (
          <div className="text-center py-12">
            <p className="text-gray-600">Your link is invalid or expired.</p>
          </div>
        )}
      </div>
    </div>
  )
}

function UnsubscribePage() {
  const [message, setMessage] = useState(null)
  const token = new URLSearchParams(window.location.search).get('token')

  useEffect(() => {
    const run = async () => {
      if (!token) {
        setMessage({ type: 'error', text: 'Missing token' })
        return
      }
      try {
        await APIService.tokenUnsubscribe(token)
        setMessage({ type: 'success', text: 'You have been unsubscribed.' })
      } catch (e) {
        setMessage({ type: 'error', text: 'Invalid or expired unsubscribe link.' })
      }
    }
    run()
  }, [token])

  return (
    <div className="max-w-xl mx-auto py-20 text-center">
      {message && (
        <Alert className={`inline-block ${message.type === 'error' ? 'border-red-500' : 'border-green-500'}`}>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

function VerifyPage() {
  const [message, setMessage] = useState(null)
  const token = new URLSearchParams(window.location.search).get('token')

  useEffect(() => {
    const run = async () => {
      if (!token) {
        setMessage({ type: 'error', text: 'Missing token' })
        return
      }
      try {
        await APIService.verifyToken(token)
        setMessage({ type: 'success', text: 'Email verified. Thank you!' })
      } catch (e) {
        setMessage({ type: 'error', text: 'Invalid or expired verification link.' })
      }
    }
    run()
  }, [token])

  return (
    <div className="max-w-xl mx-auto py-20 text-center">
      {message && (
        <Alert className={`inline-block ${message.type === 'error' ? 'border-red-500' : 'border-green-500'}`}>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}
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
          <Route path="/newsletters" element={<NewslettersPage />} />
          {/* Hidden in nav, used only via email links */}
          <Route path="/manage" element={<ManagePage />} />
          <Route path="/unsubscribe" element={<UnsubscribePage />} />
          <Route path="/verify" element={<VerifyPage />} />
        </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App

