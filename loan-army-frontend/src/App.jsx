import { useState, useEffect, useMemo } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button.jsx'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import { Textarea } from '@/components/ui/textarea.jsx'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select.jsx'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs.jsx'
import TeamMultiSelect from '@/components/ui/TeamMultiSelect.jsx'
import TeamSelect from '@/components/ui/TeamSelect.jsx'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion.jsx'
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
  BarChart3,
  Loader2
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
  static adminKey = (typeof localStorage !== 'undefined' && localStorage.getItem('loan_army_admin_key')) || null

  static setAdminKey(key) {
    this.adminKey = key
    try { localStorage.setItem('loan_army_admin_key', key || '') } catch (e) {}
  }

  static async request(endpoint, options = {}, extra = {}) {
    console.log(`🌐 Making API request to: ${API_BASE_URL}${endpoint}`, options)
    try {
      const admin = extra && extra.admin
      const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
      }
      if (admin && this.adminKey) {
        headers['X-API-Key'] = this.adminKey
      }
      const response = await fetch(`${API_BASE_URL}${endpoint}`, { headers, ...options })
      
      console.log(`📡 Response status: ${response.status} ${response.statusText}`)
      
      if (!response.ok) {
        const contentType = response.headers.get('content-type') || ''
        let parsed = null
        let errorText = ''
        try {
          if (contentType.includes('application/json')) {
            parsed = await response.json()
            errorText = parsed?.error || JSON.stringify(parsed)
          } else {
            errorText = await response.text()
          }
        } catch (_) {
          try { errorText = await response.text() } catch (_) { errorText = '' }
        }
        console.error(`❌ HTTP error response body:`, parsed || errorText)
        const err = new Error(parsed?.error || errorText || `HTTP ${response.status}`)
        err.status = response.status
        err.body = parsed || errorText
        throw err
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

  // Admin endpoints
  static async adminGetConfig() { return this.request('/admin/config', {}, { admin: true }) }
  static async adminUpdateConfig(settings) {
    return this.request('/admin/config', { method: 'POST', body: JSON.stringify({ settings }) }, { admin: true })
  }
  static async adminGetRunStatus() { return this.request('/admin/run-status', {}, { admin: true }) }
  static async adminSetRunStatus(paused) {
    return this.request('/admin/run-status', { method: 'POST', body: JSON.stringify({ runs_paused: !!paused }) }, { admin: true })
  }
  static async adminGenerateAll(dateStr) {
    return this.request('/newsletters/generate-weekly-all', { method: 'POST', body: JSON.stringify({ target_date: dateStr }) }, { admin: true })
  }
  static async adminListPendingFlags() { return this.request('/loans/flags/pending', {}, { admin: true }) }
  static async adminResolveFlag(flagId, { deactivateLoan = false, note = '' } = {}) {
    return this.request(`/loans/flags/${flagId}/resolve`, { method: 'POST', body: JSON.stringify({ action: deactivateLoan ? 'deactivate_loan' : 'none', note }) }, { admin: true })
  }
  // Admin loans CRUD
  static async adminLoansList(params = {}) {
    const q = new URLSearchParams(params)
    return this.request(`/admin/loans?${q}`, {}, { admin: true })
  }
  static async adminLoanCreate(payload) {
    return this.request('/admin/loans', { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
  }
  static async adminLoanUpdate(loanId, payload) {
    return this.request(`/admin/loans/${loanId}`, { method: 'PUT', body: JSON.stringify(payload) }, { admin: true })
  }
  static async adminLoanDeactivate(loanId) {
    return this.request(`/admin/loans/${loanId}/deactivate`, { method: 'POST' }, { admin: true })
  }
  static async adminFlags(params = {}) {
    const q = new URLSearchParams(params)
    return this.request(`/admin/flags?${q}`, {}, { admin: true })
  }
  static async adminFlagUpdate(flagId, payload) {
    return this.request(`/admin/flags/${flagId}`, { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
  }
  static async adminBackfillTeamLeagues(season) {
    return this.request(`/admin/backfill-team-leagues/${season}`, { method: 'POST' }, { admin: true })
  }
  static async adminBackfillTeamLeaguesAll(seasons) {
    const body = seasons && seasons.length ? { seasons } : {}
    return this.request(`/admin/backfill-team-leagues`, { method: 'POST', body: JSON.stringify(body) }, { admin: true })
  }
  // Admin: missing names helpers
  static async adminMissingNames(params = {}) {
    const q = new URLSearchParams(params)
    return this.request(`/admin/loans/missing-names?${q}`, {}, { admin: true })
  }
  static async adminBackfillNames(payload = {}) {
    return this.request(`/admin/loans/backfill-names`, { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
  }
  // Admin newsletters
  static async adminNewslettersList(params = {}) {
    const q = new URLSearchParams(params)
    return this.request(`/admin/newsletters?${q}`, {}, { admin: true })
  }
  static async adminNewsletterGet(id) {
    return this.request(`/admin/newsletters/${id}`, {}, { admin: true })
  }
  static async adminNewsletterUpdate(id, payload) {
    return this.request(`/admin/newsletters/${id}`, { method: 'PUT', body: JSON.stringify(payload) }, { admin: true })
  }
  static async adminNewsletterRender(id, fmt = 'web') {
    const headers = { 'Accept': 'text/html' }
    const key = this.adminKey || (typeof localStorage !== 'undefined' && localStorage.getItem('loan_army_admin_key'))
    if (key) headers['X-API-Key'] = key
    const res = await fetch(`${API_BASE_URL}/newsletters/${id}/render.${fmt}`, { headers, method: 'GET' })
    const text = await res.text()
    if (!res.ok) {
      const err = new Error(text || `HTTP ${res.status}`)
      err.status = res.status
      err.body = text
      throw err
    }
    return text
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
                <CardDescription>Use the searchable selector. ({selectedTeams.length} selected)</CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <TeamMultiSelect teams={teams} value={selectedTeams} onChange={setSelectedTeams} placeholder="Search and select teams…" />
                    <Accordion type="multiple" className="rounded-md border">
                      {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
                        <AccordionItem key={league} value={league} className="border-b last:border-b-0">
                          <AccordionTrigger className="px-4">
                            <div className="flex items-center">
                              <div className="w-3 h-3 rounded mr-2" style={{ backgroundColor: LEAGUE_COLORS[league] || '#666' }} />
                              <span className="text-sm font-semibold">{league}</span>
                              <Badge variant="secondary" className="ml-2">{leagueTeams.length}</Badge>
                            </div>
                          </AccordionTrigger>
                          <AccordionContent>
                            <div className="grid grid-cols-1 gap-2 px-4 pb-2">
                              {leagueTeams.map((team) => (
                                <label key={team.id} className="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-2 rounded">
                                  <input type="checkbox" checked={selectedTeams.includes(team.id)} onChange={() => handleTeamToggle(team.id)} className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                                  <span className="text-sm">{team.name}</span>
                                </label>
                              ))}
                            </div>
                          </AccordionContent>
                        </AccordionItem>
                      ))}
                    </Accordion>
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

// Admin page
function AdminPage() {
  const [adminKey, setAdminKey] = useState(APIService.adminKey || '')
  const [runDate, setRunDate] = useState('')
  const [seedSeason, setSeedSeason] = useState('')
  const [runStatus, setRunStatus] = useState(null)
  const [running, setRunning] = useState(false)
  const [settings, setSettings] = useState({
    brave_soft_rank: true,
    brave_site_boost: true,
    brave_cup_synonyms: true,
    search_strict_range: false,
  })
  const [flags, setFlags] = useState([])
  const [loans, setLoans] = useState([])
  const [loanFilters, setLoanFilters] = useState({ active_only: 'true', player_name: '', season: '' })
  const [loanForm, setLoanForm] = useState({ player_id: '', player_name: '', primary_team_api_id: '', loan_team_api_id: '', season: '' })
  const [missingNames, setMissingNames] = useState([])
  const [mnTeamApiId, setMnTeamApiId] = useState('')
  const [mnTeamDbId, setMnTeamDbId] = useState(null)
  const [mnBusy, setMnBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [nlFilters, setNlFilters] = useState({ published_only: '', week_start: '', week_end: '', issue_start: '', issue_end: '', created_start: '', created_end: '' })
  const [newslettersAdmin, setNewslettersAdmin] = useState([])
  const [editingNl, setEditingNl] = useState(null)
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewFormat, setPreviewFormat] = useState('web')
  const [runHistory, setRunHistory] = useState([])
  const [runTeams, setRunTeams] = useState([])
  const [selectedRunTeams, setSelectedRunTeams] = useState([])
  const [teamRunBusy, setTeamRunBusy] = useState(false)
  const [teamRunMsg, setTeamRunMsg] = useState(null)

  const load = async () => {
    try {
      const conf = await APIService.adminGetConfig()
      setSettings(s => ({
        ...s,
        brave_soft_rank: (conf.brave_soft_rank || 'true').toString().toLowerCase() !== 'false',
        brave_site_boost: (conf.brave_site_boost || 'true').toString().toLowerCase() !== 'false',
        brave_cup_synonyms: (conf.brave_cup_synonyms || 'true').toString().toLowerCase() !== 'false',
        search_strict_range: (conf.search_strict_range || 'false').toString().toLowerCase() === 'true',
      }))
      const rs = await APIService.adminGetRunStatus()
      setRunStatus(rs.runs_paused)
      const pf = await APIService.adminListPendingFlags()
      setFlags(pf)
      // initial loans set: active
      const ls = await APIService.adminLoansList({ active_only: 'true' })
      setLoans(ls)
      // initial newsletters
      const nls = await APIService.adminNewslettersList({})
      setNewslettersAdmin(nls)
    } catch (e) {
      console.error('Admin load failed', e)
    }
  }

  useEffect(() => {
    if (APIService.adminKey || (adminKey && adminKey.trim())) {
      load()
    }
  }, [adminKey])

  useEffect(() => {
    (async () => {
      try {
        const filters = { european_only: 'true' }
        const seasonYear = parseInt((loanFilters.season || '').trim(), 10)
        if (!isNaN(seasonYear)) filters.season = seasonYear
        const teams = await APIService.getTeams(filters)
        setRunTeams(Array.isArray(teams) ? teams : [])
      } catch (e) {
        setRunTeams([])
      }
    })()
  }, [loanFilters.season])

  const refreshRunHistory = async () => {
    try {
      const rows = await APIService.request('/admin/runs/history', {}, { admin: true })
      setRunHistory(Array.isArray(rows) ? rows : [])
    } catch (e) {
      // ignore
    }
  }
  useEffect(() => { if (adminKey?.trim()) refreshRunHistory() }, [adminKey])

  const saveKey = () => {
    APIService.setAdminKey(adminKey.trim())
    setMessage({ type: 'success', text: 'Admin key saved locally' })
  }
  const saveSettings = async () => {
    try {
      await APIService.adminUpdateConfig(settings)
      setMessage({ type: 'success', text: 'Settings updated' })
    } catch (e) {
      setMessage({ type: 'error', text: 'Failed to update settings' })
    }
  }
  const toggleRun = async () => {
    try {
      const next = !runStatus
      await APIService.adminSetRunStatus(next)
      setRunStatus(next)
    } catch (e) {}
  }
  const runAll = async () => {
    setRunning(true)
    setMessage(null)
    try {
      const d = runDate || new Date().toISOString().slice(0,10)
      const out = await APIService.adminGenerateAll(d)
      const results = Array.isArray(out?.results) ? out.results : []
      const ok = results.filter(r => r && r.newsletter_id).length
      const errs = results.filter(r => r && r.error).length
      const extra = results.length ? ` (${ok} ok, ${errs} errors)` : ''
      setMessage({ type: 'success', text: `Triggered run for ${out?.ran_for || d}${extra}` })
      // pull in new run-history entry
      try { await refreshRunHistory() } catch {}
    } catch (e) {
      const detail = (e && (e.body?.error || e.message)) ? `: ${String(e.body?.error || e.message)}` : ''
      setMessage({ type: 'error', text: `Failed to trigger run${detail}` })
    } finally {
      setRunning(false)
    }
  }
  const resolveFlag = async (id, deactivate=false) => {
    try {
      await APIService.adminResolveFlag(id, { deactivateLoan: deactivate })
      setFlags(flags.filter(f => f.id !== id))
    } catch (e) {}
  }
  const refreshLoans = async () => {
    const params = { ...loanFilters }
    if (params.player_name && params.player_name.trim() === '') delete params.player_name
    const ls = await APIService.adminLoansList(params)
    setLoans(ls)
  }
  const backfillTeamLeagues = async () => {
    try {
      const seasonStr = (loanFilters.season || '').trim()
      const seasonYear = parseInt(seasonStr, 10)
      if (!seasonYear) {
        setMessage({ type: 'error', text: 'Enter a valid Season (YYYY) to backfill leagues' })
        return
      }
      const res = await APIService.adminBackfillTeamLeagues(seasonYear)
      setMessage({ type: 'success', text: `Backfilled leagues for ${seasonYear} (updated ${res.updated_teams} teams)` })
      // Reload teams list for this season
      const teams = await APIService.getTeams({ european_only: 'true', season: seasonYear })
      setRunTeams(Array.isArray(teams) ? teams : [])
    } catch (e) {
      setMessage({ type: 'error', text: `Backfill failed: ${e?.body?.error || e.message}` })
    }
  }
  const backfillAllSeasons = async () => {
    try {
      const res = await APIService.adminBackfillTeamLeaguesAll()
      const updated = res?.totals?.updated_teams || 0
      const seasons = res?.totals?.seasons || 0
      setMessage({ type: 'success', text: `Backfilled all seasons (${seasons}), updated ${updated} teams` })
      // Reload current filter's teams if any
      const seasonYear = parseInt((loanFilters.season || '').trim(), 10)
      const filters = { european_only: 'true' }
      if (!isNaN(seasonYear)) filters.season = seasonYear
      const teams = await APIService.getTeams(filters)
      setRunTeams(Array.isArray(teams) ? teams : [])
    } catch (e) {
      setMessage({ type: 'error', text: `Backfill (all) failed: ${e?.body?.error || e.message}` })
    }
  }
  const listMissingNames = async () => {
    try {
      setMnBusy(true)
      const seasonStr = (loanFilters.season || '').trim()
      const seasonYear = parseInt(seasonStr, 10)
      const params = { active_only: 'true' }
      if (!isNaN(seasonYear)) params.season = seasonYear
      if (mnTeamDbId) params.primary_team_db_id = parseInt(mnTeamDbId, 10)
      else if (mnTeamApiId && mnTeamApiId.trim()) params.primary_team_api_id = parseInt(mnTeamApiId, 10)
      const rows = await APIService.adminMissingNames(params)
      setMissingNames(Array.isArray(rows) ? rows : [])
    } catch (e) {
      setMissingNames([])
      setMessage({ type: 'error', text: `List missing names failed: ${e?.body?.error || e.message}` })
    } finally {
      setMnBusy(false)
    }
  }
  const backfillMissingNames = async () => {
    try {
      setMnBusy(true)
      const seasonStr = (loanFilters.season || '').trim()
      const seasonYear = parseInt(seasonStr, 10)
      if (!seasonYear) {
        setMessage({ type: 'error', text: 'Enter Season (YYYY) first to backfill names' })
        return
      }
      const payload = { season: seasonYear, active_only: true }
      if (mnTeamDbId) payload.primary_team_db_id = parseInt(mnTeamDbId, 10)
      else if (mnTeamApiId && mnTeamApiId.trim()) payload.primary_team_api_id = parseInt(mnTeamApiId, 10)
      const res = await APIService.adminBackfillNames(payload)
      const up = res?.updated || 0
      setMessage({ type: 'success', text: `Backfilled ${up} player names` })
      await refreshLoans()
      await listMissingNames()
    } catch (e) {
      setMessage({ type: 'error', text: `Backfill names failed: ${e?.body?.error || e.message}` })
    } finally {
      setMnBusy(false)
    }
  }
  const createLoan = async () => {
    try {
      const payload = {
        player_id: parseInt(loanForm.player_id, 10),
        player_name: loanForm.player_name || undefined,
        primary_team_api_id: loanForm.primary_team_api_id ? parseInt(loanForm.primary_team_api_id, 10) : undefined,
        loan_team_api_id: loanForm.loan_team_api_id ? parseInt(loanForm.loan_team_api_id, 10) : undefined,
        season: loanForm.season ? parseInt(loanForm.season, 10) : undefined,
      }
      await APIService.adminLoanCreate(payload)
      setMessage({ type: 'success', text: 'Loan created' })
      setLoanForm({ player_id: '', player_name: '', primary_team_api_id: '', loan_team_api_id: '', season: '' })
      await refreshLoans()
    } catch (e) {
      setMessage({ type: 'error', text: `Create failed: ${e?.body?.error || e.message}` })
    }
  }
  const moveLoan = async (loan, kind, apiId) => {
    try {
      const payload = {}
      if (kind === 'primary') payload.primary_team_api_id = parseInt(apiId, 10)
      else payload.loan_team_api_id = parseInt(apiId, 10)
      await APIService.adminLoanUpdate(loan.id, payload)
      await refreshLoans()
    } catch (e) {
      setMessage({ type: 'error', text: `Update failed: ${e?.body?.error || e.message}` })
    }
  }
  const moveLoanDb = async (loan, kind, dbId) => {
    try {
      const payload = {}
      if (kind === 'primary') payload.primary_team_db_id = parseInt(dbId, 10)
      else payload.loan_team_db_id = parseInt(dbId, 10)
      await APIService.adminLoanUpdate(loan.id, payload)
      await refreshLoans()
    } catch (e) {
      setMessage({ type: 'error', text: `Update failed: ${e?.body?.error || e.message}` })
    }
  }
  const deactivateLoan = async (loan) => {
    try {
      await APIService.adminLoanDeactivate(loan.id)
      await refreshLoans()
    } catch (e) {
      setMessage({ type: 'error', text: `Deactivate failed: ${e?.body?.error || e.message}` })
    }
  }
  const teamIdToTeam = useMemo(() => {
    const m = new Map()
    for (const t of runTeams) m.set(t.id, t)
    return m
  }, [runTeams])
  const filteredLoans = useMemo(() => {
    const seasonStr = (loanFilters.season || '').trim()
    if (!seasonStr) return loans
    const seasonYear = parseInt(seasonStr, 10)
    if (!seasonYear) return loans
    const matchesSeason = (l) => {
      const ls = l.loan_season
      if (ls) {
        const start = parseInt(String(ls).split('-')[0], 10)
        return start === seasonYear
      }
      const wk = l.window_key || ''
      try {
        const start = parseInt(String(wk).split('::')[0].split('-')[0], 10)
        return start === seasonYear
      } catch {
        return false
      }
    }
    return loans.filter(matchesSeason)
  }, [loans, loanFilters.season])
  const loansByLeague = useMemo(() => {
    const leagues = {}
    for (const l of filteredLoans) {
      const t = teamIdToTeam.get(l.primary_team_id)
      const league = t?.league_name || 'Other'
      if (!leagues[league]) leagues[league] = {}
      const teamKey = l.primary_team_id
      if (!leagues[league][teamKey]) leagues[league][teamKey] = { teamId: teamKey, teamName: l.primary_team_name, loans: [] }
      leagues[league][teamKey].loans.push(l)
    }
    return leagues
  }, [filteredLoans, teamIdToTeam])
  const refreshNewsletters = async () => {
    const params = {}
    if (nlFilters.published_only) params.published_only = nlFilters.published_only
    if (nlFilters.week_start && nlFilters.week_end) {
      params.week_start = nlFilters.week_start
      params.week_end = nlFilters.week_end
    }
    if (nlFilters.issue_start && nlFilters.issue_end) {
      params.issue_start = nlFilters.issue_start
      params.issue_end = nlFilters.issue_end
    }
    if (nlFilters.created_start && nlFilters.created_end) {
      params.created_start = nlFilters.created_start
      params.created_end = nlFilters.created_end
    }
    const rows = await APIService.adminNewslettersList(params)
    setNewslettersAdmin(rows)
  }
  const resetNewsletterFilters = () => setNlFilters({ published_only: '', week_start: '', week_end: '', issue_start: '', issue_end: '', created_start: '', created_end: '' })
  const startEditNewsletter = async (row) => {
    const full = await APIService.adminNewsletterGet(row.id)
    setEditingNl(full)
    setPreviewHtml('')
  }
  const saveNewsletter = async () => {
    if (!editingNl) return
    try {
      const payload = {
        title: editingNl.title,
        content_json: (() => { try { return typeof editingNl.content === 'string' ? JSON.parse(editingNl.content) : editingNl.content } catch { return editingNl.content } })(),
        published: !!editingNl.published,
        issue_date: editingNl.issue_date?.slice(0,10),
        week_start_date: editingNl.week_start_date?.slice(0,10),
        week_end_date: editingNl.week_end_date?.slice(0,10),
      }
      await APIService.adminNewsletterUpdate(editingNl.id, payload)
      setMessage({ type: 'success', text: 'Newsletter updated' })
      setEditingNl(null)
      await refreshNewsletters()
    } catch (e) {
      setMessage({ type: 'error', text: `Save failed: ${e?.body?.error || e.message}` })
    }
  }
  const refreshPreview = async () => {
    if (!editingNl) return
    try {
      const html = await APIService.adminNewsletterRender(editingNl.id, previewFormat === 'email' ? 'email' : 'web')
      setPreviewHtml(html)
    } catch (e) {
      setPreviewHtml(`<div style="padding:12px;color:#b91c1c;background:#fee2e2;border:1px solid #fecaca;">Failed to load preview: ${String(e.body || e.message || e)}</div>`) 
    }
  }

  useEffect(() => {
    if (editingNl && editingNl.id) {
      refreshPreview()
    }
  }, [editingNl, previewFormat])

  return (
    <div className="max-w-6xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0 space-y-6">
        <h1 className="text-3xl font-bold">Admin</h1>
        {message && (
          <div className={`p-3 rounded ${message.type==='error'?'bg-red-100 text-red-700':'bg-green-100 text-green-700'}`}>{message.text}</div>
        )}
        <div className="sticky top-2 z-10 bg-white/80 backdrop-blur border rounded p-2 flex flex-wrap gap-2">
          <a href="#admin-api"><Button size="sm" variant="outline">API Key</Button></a>
          <a href="#admin-runs"><Button size="sm" variant="outline">Runs</Button></a>
          <a href="#admin-seed"><Button size="sm" variant="outline">Seed Top-5</Button></a>
          <a href="#admin-loans"><Button size="sm" variant="outline">Loans Manager</Button></a>
          <a href="#admin-newsletters"><Button size="sm" variant="outline">Newsletters</Button></a>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div id="admin-api" className="border rounded p-4">
            <h2 className="font-semibold mb-3">API Key</h2>
            <input className="border rounded p-2 w-full" placeholder="Admin API Key" value={adminKey} onChange={e=>setAdminKey(e.target.value)} />
            <div className="mt-2">
              <Button onClick={saveKey}>Save Key</Button>
            </div>
          </div>
          <div id="admin-runs" className="border rounded p-4">
            <h2 className="font-semibold mb-3">Runs</h2>
            <div className="flex gap-2 items-center">
              <input type="date" className="border rounded p-2" value={runDate} onChange={e=>setRunDate(e.target.value)} />
              <Button onClick={()=>runAll(false)} disabled={running}>
                <span className="inline-flex items-center gap-2">
                  {running && <Loader2 className="h-4 w-4 animate-spin" />}
                  {running ? 'Running…' : 'Run All'}
                </span>
              </Button>
              {running && (
                <span className="text-xs text-muted-foreground">Processing newsletter generation…</span>
              )}
            </div>
            <div className="mt-4">
              <div className="text-sm font-semibold mb-2">Run Specific Teams</div>
              <TeamMultiSelect
                teams={runTeams}
                value={selectedRunTeams}
                onChange={setSelectedRunTeams}
                placeholder="Search and select teams…"
              />
              <div id="admin-seed" className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2">
                <div className="flex flex-col">
                  <span className="text-xs text-muted-foreground">Seed season (YYYY)</span>
                  <input
                    className="border rounded p-2 text-sm"
                    placeholder="2025"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={seedSeason}
                    onChange={(e)=>{ const y=(e.target.value||'').replace(/[^0-9]/g,'').slice(0,4); setSeedSeason(y) }}
                  />
                </div>
                <div className="flex items-end">
                  <Button size="sm" variant="outline" onClick={async ()=>{
                    const y = parseInt((seedSeason || (runDate||'').slice(0,4)),10)
                    if (!y) { setTeamRunMsg({ type:'error', text:'Enter a valid season year'}); return }
                    try{
                      setTeamRunBusy(true); setTeamRunMsg(null)
                      const res = await APIService.request('/admin/loans/seed-top5', { method:'POST', body: JSON.stringify({ season: y, overwrite: true }) }, { admin: true })
                      setTeamRunMsg({ type: 'success', text: `Seeded ${res.created} players (skipped ${res.skipped}) for ${res.season}` })
                      await refreshLoans()
                      try { await refreshRunHistory() } catch {}
                    }catch(e){ setTeamRunMsg({ type:'error', text: `Seed failed: ${e?.body?.error || e.message}` }) }
                    finally{ setTeamRunBusy(false) }
                  }} disabled={teamRunBusy}>Seed Top-5 Loans</Button>
                </div>
                <div className="flex items-end">
                  <Button size="sm" variant="ghost" onClick={async ()=>{
                    const y = parseInt((seedSeason || (runDate||'').slice(0,4)),10)
                    if (!y) { setTeamRunMsg({ type:'error', text:'Enter a valid season year'}); return }
                    try{
                      setTeamRunBusy(true); setTeamRunMsg(null)
                      const res = await APIService.request('/admin/loans/seed-top5', { method:'POST', body: JSON.stringify({ season: y, dry_run: true }) }, { admin: true })
                      const wouldCreate = (res.details||[]).filter(d=>d.status==='created').length
                      setTeamRunMsg({ type: 'success', text: `Dry-run: would create ${wouldCreate} of ${res.candidates}` })
                      try { await refreshRunHistory() } catch {}
                    }catch(e){ setTeamRunMsg({ type:'error', text: `Dry-run failed: ${e?.body?.error || e.message}` }) }
                    finally{ setTeamRunBusy(false) }
                  }} disabled={teamRunBusy}>Dry-run</Button>
                </div>
              </div>
              <div className="mt-2 flex gap-2 items-center flex-wrap">
                <Button size="sm" onClick={async ()=>{
                  if (!selectedRunTeams.length) return
                  setTeamRunBusy(true); setTeamRunMsg(null)
                  const d = runDate || new Date().toISOString().slice(0,10)
                  let ok=0, errs=0
                  for (const tid of selectedRunTeams) {
                    try {
                      await APIService.generateNewsletter({ team_id: tid, target_date: d, type: 'weekly' })
                      ok++
                    } catch (e) { errs++ }
                  }
                  setTeamRunMsg({ type: errs? 'error':'success', text: `OpenAI run: ${ok} ok, ${errs} errors` })
                  setTeamRunBusy(false)
                }} disabled={teamRunBusy || selectedRunTeams.length===0}>Run Selected (OpenAI)</Button>
                <Button size="sm" variant="secondary" onClick={async ()=>{
                  const y = parseInt((seedSeason || (runDate||'').slice(0,4)),10)
                  if (!y) { setTeamRunMsg({ type:'error', text:'Enter a valid season year above'}); return }
                  if (!selectedRunTeams.length) return
                  setTeamRunBusy(true); setTeamRunMsg(null)
                  let created=0, errs=0
                  for (const dbId of selectedRunTeams) {
                    try {
                      const res = await APIService.request('/admin/loans/seed-team', { method:'POST', body: JSON.stringify({ season: y, team_db_id: dbId, overwrite: true }) }, { admin: true })
                      created += (res.created||0)
                    } catch (e) { errs++ }
                  }
                  setTeamRunMsg({ type: errs? 'error':'success', text: `Seeded ${created} players across ${selectedRunTeams.length} team(s)` })
                  setTeamRunBusy(false)
                  await refreshLoans()
                  try { await refreshRunHistory() } catch {}
                }} disabled={teamRunBusy || selectedRunTeams.length===0}>Seed Selected Team(s)</Button>
                {(teamRunBusy || running) && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                {(teamRunBusy || running) && <span className="text-xs text-muted-foreground">Working…</span>}
              </div>
              {teamRunMsg && (
                <div className={`mt-2 p-2 rounded text-sm ${teamRunMsg.type==='error'?'bg-red-100 text-red-700':'bg-green-100 text-green-700'}`}>{teamRunMsg.text}</div>
              )}
              <div className="mt-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold">Recent Runs</div>
                  <Button size="sm" variant="ghost" onClick={refreshRunHistory}>Refresh</Button>
                </div>
                {runHistory.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No recent runs.</div>
                ) : (
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div className="border rounded">
                      <div className="px-2 py-1 text-xs font-semibold bg-gray-50 border-b">Newsletter Runs</div>
                      <div className="max-h-48 overflow-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-left">
                              <th className="p-2">Time</th>
                              <th className="p-2">Info</th>
                            </tr>
                          </thead>
                          <tbody>
                            {runHistory.filter(r => (r.kind||'').startsWith('newsletter')).slice(0,20).map((r, i) => (
                              <tr key={i} className="border-t">
                                <td className="p-2 whitespace-nowrap">{r.ts?.replace('T',' ').slice(0,19) || ''}</td>
                                <td className="p-2 truncate">{r.message || r.text || r.detail || ''}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                    <div className="border rounded">
                      <div className="px-2 py-1 text-xs font-semibold bg-gray-50 border-b">Seeding Runs</div>
                      <div className="max-h-48 overflow-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-left">
                              <th className="p-2">Time</th>
                              <th className="p-2">Type</th>
                              <th className="p-2">Details</th>
                            </tr>
                          </thead>
                          <tbody>
                            {runHistory.filter(r => ['seed-top5','seed-team','seed-top5-dry'].includes(r.kind)).slice(0,20).map((r, i) => (
                              <tr key={i} className="border-t">
                                <td className="p-2 whitespace-nowrap">{r.ts?.replace('T',' ').slice(0,19) || ''}</td>
                                <td className="p-2 whitespace-nowrap">{r.kind}</td>
                                <td className="p-2 truncate">
                                  {r.season ? `Szn ${r.season}` : ''} {r.window_key ? `• ${r.window_key}` : ''} {r.team_db_id ? `• team_db_id=${r.team_db_id}` : ''} {r.api_team_id ? `• api_id=${r.api_team_id}` : ''}
                                  {r.message ? ` • ${r.message}` : ''}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <span className="text-sm">Runs paused:</span>
              <Button variant={runStatus? 'default':'outline'} onClick={toggleRun} disabled={running}>{runStatus? 'Resume':'Pause'}</Button>
            </div>
          </div>
          <div id="admin-loans" className="border rounded p-4 md:col-span-2">
            <h2 className="font-semibold mb-3">Loans Manager</h2>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="space-y-2">
                <div className="font-medium">Filters</div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 items-end">
                  <label className="text-sm flex items-center gap-2">
                    <input type="checkbox" checked={loanFilters.active_only === 'true'} onChange={e=>setLoanFilters({...loanFilters, active_only: e.target.checked ? 'true' : 'false'})} />
                    <span>Active only</span>
                  </label>
                  <div className="flex flex-col">
                    <span className="text-xs text-muted-foreground">Player name</span>
                    <input className="border rounded p-2 text-sm w-full" placeholder="e.g., Smith" value={loanFilters.player_name} onChange={e=>setLoanFilters({...loanFilters, player_name: e.target.value})} />
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs text-muted-foreground">Season (YYYY)</span>
                    <input type="number" inputMode="numeric" pattern="[0-9]*" className="border rounded p-2 text-sm w-full" placeholder="2025" value={loanFilters.season} onChange={e=>setLoanFilters({...loanFilters, season: e.target.value})} />
                  </div>
                  <div className="flex sm:justify-end">
                    <Button size="sm" variant="outline" className="w-full sm:w-auto" onClick={refreshLoans}>Apply</Button>
                  </div>
                </div>
                <div className="text-xs text-gray-500">Backfill helpers</div>
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  <Button size="sm" variant="outline" onClick={backfillTeamLeagues}>Backfill team leagues for season</Button>
                  <Button size="sm" variant="ghost" onClick={backfillAllSeasons}>Backfill all seasons</Button>
                  <div className="flex items-center gap-2">
                    <TeamSelect
                      teams={runTeams}
                      value={mnTeamDbId}
                      onChange={setMnTeamDbId}
                      placeholder="Select team (optional)…"
                    />
                    <span className="text-xs text-gray-500">or API ID:</span>
                    <input className="border rounded p-2 text-sm w-36" placeholder="Team API ID (opt)" value={mnTeamApiId} onChange={e=>setMnTeamApiId(e.target.value)} />
                  </div>
                  <Button size="sm" variant="outline" onClick={listMissingNames} disabled={mnBusy}>{mnBusy? 'Checking…':'Find missing names (season)'}</Button>
                  <Button size="sm" onClick={backfillMissingNames} disabled={mnBusy}>Backfill missing names (season)</Button>
                </div>
                {missingNames && missingNames.length > 0 && (
                  <div className="mt-3">
                    <div className="text-xs font-semibold mb-1">Missing names ({missingNames.length})</div>
                    <div className="max-h-56 overflow-auto border rounded">
                      <table className="min-w-full text-xs">
                        <thead className="bg-gray-50">
                          <tr className="text-left">
                            <th className="p-2">Loan ID</th>
                            <th className="p-2">Player ID</th>
                            <th className="p-2">Player name</th>
                            <th className="p-2">Primary</th>
                            <th className="p-2">Loan team</th>
                            <th className="p-2">Window</th>
                          </tr>
                        </thead>
                        <tbody>
                          {missingNames.map(m => (
                            <tr key={m.id} className="border-t">
                              <td className="p-2 whitespace-nowrap">{m.id}</td>
                              <td className="p-2 whitespace-nowrap">{m.player_id}</td>
                              <td className="p-2">{m.player_name || ''}</td>
                              <td className="p-2 whitespace-nowrap">{m.primary_team_name}</td>
                              <td className="p-2 whitespace-nowrap">{m.loan_team_name}</td>
                              <td className="p-2 whitespace-nowrap">{m.window_key}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
              <div className="space-y-2 lg:col-span-2">
                <div className="font-medium">Add Loan</div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                  <input className="border rounded p-2 text-sm" placeholder="Player ID" value={loanForm.player_id} onChange={e=>setLoanForm({...loanForm, player_id: e.target.value})} />
                  <input className="border rounded p-2 text-sm" placeholder="Player name (opt)" value={loanForm.player_name} onChange={e=>setLoanForm({...loanForm, player_name: e.target.value})} />
                  <input className="border rounded p-2 text-sm" placeholder="Primary Team API ID" value={loanForm.primary_team_api_id} onChange={e=>setLoanForm({...loanForm, primary_team_api_id: e.target.value})} />
                  <input className="border rounded p-2 text-sm" placeholder="Loan Team API ID" value={loanForm.loan_team_api_id} onChange={e=>setLoanForm({...loanForm, loan_team_api_id: e.target.value})} />
                  <input className="border rounded p-2 text-sm" placeholder="Season (YYYY)" value={loanForm.season} onChange={e=>setLoanForm({...loanForm, season: e.target.value})} />
                </div>
                <Button size="sm" onClick={createLoan} disabled={!loanForm.player_id || !(loanForm.primary_team_api_id && loanForm.loan_team_api_id)}>Create</Button>
              </div>
            </div>
            <div className="mt-4">
              {loans.length === 0 ? (
                <div className="text-sm text-gray-600">No loans found with current filters.</div>
              ) : (
                <Accordion type="multiple" className="rounded-md border">
                  {Object.entries(loansByLeague).map(([league, teamsMap]) => {
                    const teamsArr = Object.values(teamsMap)
                    const loanCount = teamsArr.reduce((sum, t) => sum + t.loans.length, 0)
                    return (
                      <AccordionItem key={league} value={league} className="border-b last:border-b-0">
                        <AccordionTrigger className="px-4">
                          <div className="flex items-center justify-between w-full">
                            <div className="font-semibold">{league}</div>
                            <div className="text-xs text-muted-foreground">{teamsArr.length} teams • {loanCount} loans</div>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent>
                          <div className="px-4 pb-4">
                            <Accordion type="multiple" className="rounded-md border">
                              {teamsArr.map((t) => (
                                <AccordionItem key={t.teamId} value={String(t.teamId)} className="border-b last:border-b-0">
                                  <AccordionTrigger className="px-4">
                                    <div className="flex items-center justify-between w-full">
                                      <div className="font-medium">{t.teamName}</div>
                                      <div className="text-xs text-muted-foreground">{t.loans.length} loans</div>
                                    </div>
                                  </AccordionTrigger>
                                  <AccordionContent>
                                    <div className="overflow-x-auto">
                                      <table className="min-w-full text-sm">
                                        <thead>
                                          <tr className="text-left border-b">
                                            <th className="p-2">Player</th>
                                            <th className="p-2">Primary → Loan</th>
                                            <th className="p-2">Active</th>
                                            <th className="p-2">Actions</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {t.loans.map((l) => (
                                            <tr key={l.id} className="border-b">
                                              <td className="p-2 whitespace-nowrap">
                                                <div className="font-medium">{l.player_name}</div>
                                                <div className="text-gray-500">#{l.player_id}</div>
                                              </td>
                                              <td className="p-2">
                                                <div className="flex gap-2 items-center">
                                                  <span className="text-gray-700">{l.primary_team_name}</span>
                                                  <span>→</span>
                                                  <span className="text-gray-700">{l.loan_team_name}</span>
                                                </div>
                                                <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                                                  <TeamSelect
                                                    teams={runTeams}
                                                    value={l.primary_team_id}
                                                    onChange={(id)=> moveLoanDb(l, 'primary', id)}
                                                    placeholder="Change primary team…"
                                                  />
                                                  <TeamSelect
                                                    teams={runTeams}
                                                    value={l.loan_team_id}
                                                    onChange={(id)=> moveLoanDb(l, 'loan', id)}
                                                    placeholder="Change loan team…"
                                                  />
                                                </div>
                                              </td>
                                              <td className="p-2">{l.is_active ? 'Yes' : 'No'}</td>
                                              <td className="p-2">
                                                <div className="flex gap-2">
                                                  {l.is_active && (<Button size="sm" variant="outline" onClick={()=>deactivateLoan(l)}>Deactivate</Button>)}
                                                </div>
                                              </td>
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  </AccordionContent>
                                </AccordionItem>
                              ))}
                            </Accordion>
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    )
                  })}
                </Accordion>
              )}
            </div>
          </div>
          <div id="admin-newsletters" className="border rounded p-4 md:col-span-2">
            <h2 className="font-semibold mb-3">Newsletters Manager</h2>
            <div className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="md:col-span-1 border rounded p-2">
                  <div className="text-xs font-semibold mb-1">Issue date (primary)</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <input type="date" className="border rounded p-2 text-sm" value={nlFilters.issue_start} onChange={e=>setNlFilters({...nlFilters, issue_start: e.target.value})} />
                    <input type="date" className="border rounded p-2 text-sm" value={nlFilters.issue_end} onChange={e=>setNlFilters({...nlFilters, issue_end: e.target.value})} />
                  </div>
                </div>
                <div className="md:col-span-1 border rounded p-2">
                  <div className="text-xs font-semibold mb-1">Created date</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <input type="date" className="border rounded p-2 text-sm" value={nlFilters.created_start} onChange={e=>setNlFilters({...nlFilters, created_start: e.target.value})} />
                    <input type="date" className="border rounded p-2 text-sm" value={nlFilters.created_end} onChange={e=>setNlFilters({...nlFilters, created_end: e.target.value})} />
                  </div>
                </div>
                <div className="md:col-span-1 border rounded p-2">
                  <div className="text-xs font-semibold mb-1">Week range (optional)</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <input type="date" className="border rounded p-2 text-sm" value={nlFilters.week_start} onChange={e=>setNlFilters({...nlFilters, week_start: e.target.value})} />
                    <input type="date" className="border rounded p-2 text-sm" value={nlFilters.week_end} onChange={e=>setNlFilters({...nlFilters, week_end: e.target.value})} />
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-sm flex items-center gap-1">
                  <span>Published only</span>
                  <input type="checkbox" checked={nlFilters.published_only === 'true'} onChange={e=>setNlFilters({...nlFilters, published_only: e.target.checked ? 'true' : ''})} />
                </label>
                <div className="ml-auto flex gap-2">
                  <Button size="sm" variant="outline" onClick={refreshNewsletters}>Apply filters</Button>
                  <Button size="sm" variant="ghost" onClick={resetNewsletterFilters}>Reset</Button>
                </div>
              </div>
            </div>
            <div className="mt-4">
              {newslettersAdmin.length === 0 ? (
                <div className="text-sm text-gray-600">No newsletters.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-left border-b">
                        <th className="p-2">Team</th>
                        <th className="p-2">Title</th>
                        <th className="p-2">Week</th>
                        <th className="p-2">Published</th>
                        <th className="p-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {newslettersAdmin.map(n => (
                        <tr key={n.id} className="border-b">
                          <td className="p-2 whitespace-nowrap">{n.team_name}</td>
                          <td className="p-2">{n.title}</td>
                          <td className="p-2">{n.week_start_date ? `${n.week_start_date} → ${n.week_end_date}` : ''}</td>
                          <td className="p-2">{n.published ? `Yes (${n.published_date?.slice(0,10) || ''})` : 'No'}</td>
                          <td className="p-2">
                            <Button size="sm" variant="outline" onClick={()=>startEditNewsletter(n)}>View/Edit</Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            {editingNl && (
              <div className="mt-4 border-t pt-4">
                <div className="font-medium mb-2">Editing: {editingNl.title}</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <input className="border rounded p-2 text-sm" value={editingNl.title || ''} onChange={e=>setEditingNl({...editingNl, title: e.target.value})} />
                  <label className="text-sm flex items-center gap-2">
                    <input type="checkbox" checked={!!editingNl.published} onChange={e=>setEditingNl({...editingNl, published: e.target.checked})} /> Published
                  </label>
                  <input type="date" className="border rounded p-2 text-sm" value={editingNl.issue_date?.slice(0,10) || ''} onChange={e=>setEditingNl({...editingNl, issue_date: e.target.value})} />
                  <div className="flex gap-2">
                    <input type="date" className="border rounded p-2 text-sm" value={editingNl.week_start_date?.slice(0,10) || ''} onChange={e=>setEditingNl({...editingNl, week_start_date: e.target.value})} />
                    <input type="date" className="border rounded p-2 text-sm" value={editingNl.week_end_date?.slice(0,10) || ''} onChange={e=>setEditingNl({...editingNl, week_end_date: e.target.value})} />
                  </div>
                  <div className="md:col-span-2 grid grid-cols-1 lg:grid-cols-2 gap-3">
                    <div className="flex flex-col gap-2">
                      <div className="text-sm font-medium">Content JSON</div>
                      <textarea className="border rounded p-2 text-sm" rows="16" value={(() => { try { return typeof editingNl.content === 'string' ? editingNl.content : JSON.stringify(editingNl.content || {}, null, 2) } catch { return String(editingNl.content || '') } })()} onChange={e=>setEditingNl({...editingNl, content: e.target.value})} />
                    </div>
                    <div className="flex flex-col gap-2">
                      <div className="text-sm font-medium">Preview</div>
                      <div className="border rounded bg-white p-4 max-h-[520px] overflow-auto">
                        {(() => {
                          try {
                            const obj = (() => { try { return typeof editingNl.content === 'string' ? JSON.parse(editingNl.content) : (editingNl.content || {}) } catch { return {} } })()
                            return (
                              <div className="space-y-4">
                                <div className="bg-gradient-to-r from-blue-50 to-gray-50 p-4 rounded border-l-4 border-blue-500">
                                  <div className="text-xl font-bold text-gray-900 mb-1">{obj.title || editingNl.title}</div>
                                  {obj.range && (
                                    <div className="text-xs text-gray-600">Week: {obj.range[0]} - {obj.range[1]}</div>
                                  )}
                                  {obj.summary && (
                                    <div className="text-gray-700 leading-relaxed mt-2">{obj.summary}</div>
                                  )}
                                </div>
                                {obj.highlights && Array.isArray(obj.highlights) && obj.highlights.length > 0 && (
                                  <div className="bg-yellow-50 p-3 rounded border-l-4 border-yellow-400">
                                    <div className="text-sm font-semibold text-gray-900 mb-2">Key Highlights</div>
                                    <ul className="list-disc ml-5 space-y-1">
                                      {obj.highlights.map((h, i) => (<li key={i} className="text-sm text-gray-700">{h}</li>))}
                                    </ul>
                                  </div>
                                )}
                                {obj.sections && obj.sections.length > 0 && (
                                  <div className="space-y-3">
                                    {obj.sections.map((sec, si) => (
                                      <div key={si} className="bg-white border rounded">
                                        {sec.title && (
                                          <div className="bg-gray-100 px-3 py-2 border-b text-sm font-semibold">{sec.title}</div>
                                        )}
                                        <div className="p-3 space-y-2">
                                          {sec.items && sec.items.map((it, ii) => (
                                            <div key={ii} className="border-l-4 border-blue-200 pl-3 py-1">
                                              <div className="flex flex-wrap items-center gap-2">
                                                {it.player_name && (<span className="font-semibold text-gray-900">{it.player_name}</span>)}
                                                {it.loan_team && (<span className="bg-blue-100 text-blue-800 px-2 py-0.5 rounded text-xs">→ {it.loan_team}</span>)}
                                                {it.stats && (
                                                  <div className="flex gap-1 text-xs">
                                                    {it.stats.goals > 0 && (<span className="bg-green-100 text-green-800 px-1 rounded">{it.stats.goals}G</span>)}
                                                    {it.stats.assists > 0 && (<span className="bg-purple-100 text-purple-800 px-1 rounded">{it.stats.assists}A</span>)}
                                                    {it.stats.minutes > 0 && (<span className="bg-blue-100 text-blue-800 px-1 rounded">{it.stats.minutes}'</span>)}
                                                  </div>
                                                )}
                                              </div>
                                              {it.week_summary && (<div className="text-sm text-gray-700">{it.week_summary}</div>)}
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )
                          } catch {
                            return <div className="text-sm text-gray-600">Unable to render preview.</div>
                          }
                        })()}
                      </div>
                    </div>
                    <div className="flex flex-col gap-2">
                      <div className="text-sm font-medium flex items-center gap-2">
                        Full Render
                        <div className="ml-auto flex items-center gap-2">
                          <Button size="sm" variant={previewFormat==='web'?'default':'outline'} onClick={()=>setPreviewFormat('web')}>Web</Button>
                          <Button size="sm" variant={previewFormat==='email'?'default':'outline'} onClick={()=>setPreviewFormat('email')}>Email</Button>
                          <Button size="sm" variant="ghost" onClick={refreshPreview}>Reload</Button>
                        </div>
                      </div>
                      <div className="border rounded bg-white max-h-[520px] overflow-auto">
                        {previewHtml ? (
                          <div dangerouslySetInnerHTML={{ __html: previewHtml }} />
                        ) : (
                          <div className="p-3 text-sm text-gray-500">No preview loaded yet.</div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={saveNewsletter}>Save</Button>
                  <Button size="sm" variant="outline" onClick={()=>setEditingNl(null)}>Cancel</Button>
                </div>
              </div>
            )}
          </div>
          <div className="border rounded p-4">
            <h2 className="font-semibold mb-3">Newsletter Settings</h2>
            <div className="space-y-2">
              {[
                ['brave_soft_rank','Soft Rank (quality-first ordering)'],
                ['brave_site_boost','Site Boost (local/club sources)'],
                ['brave_cup_synonyms','Cup Synonyms (EFL/FA/League)'],
                ['search_strict_range','Strict Date Window (drop undated)'],
              ].map(([k,label]) => (
                <label key={k} className="flex items-center gap-2">
                  <input type="checkbox" checked={!!settings[k]} onChange={e=>setSettings({...settings, [k]: e.target.checked})} />
                  <span>{label}</span>
                </label>
              ))}
            </div>
            <div className="mt-2">
              <Button onClick={saveSettings}>Save Settings</Button>
            </div>
          </div>
          <div className="border rounded p-4">
            <h2 className="font-semibold mb-3">Pending Player Flags</h2>
            {flags.length===0 ? (
              <p className="text-sm text-gray-600">No pending flags.</p>
            ) : (
              <div className="space-y-3">
                {flags.map(f => (
                  <div key={f.id} className="border rounded p-3">
                    <div className="text-sm">Flag #{f.id}</div>
                    <div className="text-sm">Player API: {f.player_api_id}</div>
                    <div className="text-sm">Primary Team API: {f.primary_team_api_id}</div>
                    {f.loan_team_api_id && <div className="text-sm">Loan Team API: {f.loan_team_api_id}</div>}
                    {f.season && <div className="text-sm">Season: {f.season}</div>}
                    <div className="text-sm">Reason: {f.reason}</div>
                    <div className="mt-2 flex gap-2">
                      <Button size="sm" onClick={()=>resolveFlag(f.id,false)}>Resolve</Button>
                      <Button size="sm" variant="outline" onClick={()=>resolveFlag(f.id,true)}>Resolve + Deactivate Loan</Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
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
    { path: '/teams', label: 'Browse Teams', icon: Users },
    { path: '/newsletters', label: 'Newsletters', icon: FileText },
    { path: '/admin', label: 'Admin', icon: Settings }
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
            <Link to="/teams">
              <Button size="lg" variant="outline">
                <Users className="h-5 w-5 mr-2" />
                Browse Teams
              </Button>
            </Link>
            <Link to="/admin">
              <Button size="lg">
                <Settings className="h-5 w-5 mr-2" />
                Admin
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
              <CardDescription>Choose teams using the searchable selector. ({selectedTeams.length} selected)</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="text-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                </div>
              ) : (
                <div className="space-y-4">
                  <TeamMultiSelect teams={teams} value={selectedTeams} onChange={setSelectedTeams} placeholder="Search and select teams…" />
                  <Accordion type="multiple" className="rounded-md border">
                    {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
                      <AccordionItem key={league} value={league} className="border-b last:border-b-0">
                        <AccordionTrigger className="px-4">
                          <div className="flex items-center">
                            <div className="w-4 h-4 rounded mr-2" style={{ backgroundColor: LEAGUE_COLORS[league] || '#666' }} />
                            <span className="font-medium">{league}</span>
                            <Badge variant="secondary" className="ml-2">{leagueTeams.length}</Badge>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent>
                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 px-4 pb-2">
                            {leagueTeams.map((team) => (
                              <div key={team.id} className={`p-3 border rounded-lg cursor-pointer transition-colors ${selectedTeams.includes(team.id) ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'}`} onClick={() => handleTeamToggle(team.id)}>
                                <div className="flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{team.name}</div>
                                    <div className="text-sm text-gray-500">{team.current_loaned_out_count} active loans</div>
                                  </div>
                                  {selectedTeams.includes(team.id) && (<CheckCircle className="h-5 w-5 text-blue-600" />)}
                                </div>
                              </div>
                            ))}
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
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
  const [selectedTeams, setSelectedTeams] = useState([])
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState(null)

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
  const handleTeamToggle = (teamId) => {
    setSelectedTeams((prev) => prev.includes(teamId) ? prev.filter((id) => id !== teamId) : [...prev, teamId])
  }

  const handleCardClick = (e, teamId) => {
    const tag = (e.target.tagName || '').toLowerCase()
    if (['button', 'input', 'textarea', 'select', 'a', 'svg', 'path'].includes(tag)) return
    handleTeamToggle(teamId)
  }

  const handleBulkSubscribe = async () => {
    if (!email.trim() || selectedTeams.length === 0) {
      setMessage({ type: 'error', text: 'Please enter email and select at least one team' })
      return
    }
    setSubmitting(true)
    try {
      await APIService.createSubscriptions({ email: email.trim(), team_ids: selectedTeams })
      setMessage({ type: 'success', text: `Successfully subscribed to ${selectedTeams.length} teams!` })
      setSelectedTeams([])
      setEmail('')
    } catch (e) {
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
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="flex flex-col gap-4 mb-6 sticky top-0 bg-gray-50/80 backdrop-blur supports-[backdrop-filter]:bg-gray-50/60 z-10 p-3 rounded-b">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">European Teams</h1>
              <div className="flex items-center space-x-2 mb-2">
                <Badge variant="secondary" className="bg-green-100 text-green-800 border-green-300">
                  <Calendar className="h-3 w-3 mr-1" />
                  Current Season
                </Badge>
              </div>
              <p className="text-lg text-gray-600">Browse current season teams from Europe's top 5 leagues</p>
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
          <TeamMultiSelect
            teams={teams}
            value={selectedTeams}
            onChange={setSelectedTeams}
            placeholder="Search and select teams…"
            className="w-full"
          />
          <Card>
            <CardHeader>
              <CardTitle>Subscribe to Team Updates</CardTitle>
              <CardDescription>Select multiple teams using the selector above, then subscribe.</CardDescription>
            </CardHeader>
            <CardContent>
              {message && (
                <Alert className={`mb-4 ${message.type === 'error' ? 'border-red-500' : 'border-green-500'}`}>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{message.text}</AlertDescription>
                </Alert>
              )}
              <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-end">
                <div className="flex-1">
                  <Label htmlFor="bulk-email">Email Address</Label>
                  <Input id="bulk-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="your.email@example.com" required />
                </div>
                <Button onClick={handleBulkSubscribe} disabled={submitting || selectedTeams.length === 0} className="bg-blue-600 hover:bg-blue-700">
                  {submitting ? 'Subscribing…' : `Subscribe to ${selectedTeams.length} Team${selectedTeams.length !== 1 ? 's' : ''}`}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading teams...</p>
          </div>
        ) : (
          <Accordion type="single" collapsible className="space-y-4">
            {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
              <AccordionItem key={league} value={league} className="border rounded-md">
                <AccordionTrigger className="px-4">
                  <div className="flex items-center">
                    <div className="w-6 h-6 rounded mr-3" style={{ backgroundColor: LEAGUE_COLORS[league] || '#666' }} />
                    <span className="text-lg font-semibold">{league}</span>
                    <Badge variant="secondary" className="ml-2">{leagueTeams.length} teams</Badge>
                  </div>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 px-4">
                    {leagueTeams.map((team) => (
                      <Card key={team.id} className={`hover:shadow-lg transition-shadow ${selectedTeams.includes(team.id) ? 'ring-2 ring-blue-400' : ''}`} onClick={(e) => handleCardClick(e, team.id)}>
                        <CardHeader className="pb-3">
                          <CardTitle className="text-lg">{team.name}</CardTitle>
                          <CardDescription>
                            {team.country} • Founded {team.founded || 'N/A'}
                          </CardDescription>
                        </CardHeader>
                        <CardContent>
                          <div className="flex items-center gap-2 mb-3">
                            <input type="checkbox" checked={selectedTeams.includes(team.id)} onChange={() => handleTeamToggle(team.id)} className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                            <span className="text-sm">{selectedTeams.includes(team.id) ? 'Selected' : 'Select team'}</span>
                          </div>
                          <div className="flex justify-between items-center">
                            <div className="text-sm text-gray-600">
                              <div className="flex items-center">
                                <TrendingUp className="h-4 w-4 mr-1" />
                                {team.current_loaned_out_count} active loans
                              </div>
                            </div>
                            <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); toggleExpand(team.id) }}>
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
                                        <textarea className="w-full border rounded p-2 text-sm" rows="3" placeholder="Why is this incorrect?" value={flagState.reason} onChange={(e) => setFlagState(prev => ({ ...prev, reason: e.target.value }))} />
                                        <input type="email" className="w-full border rounded p-2 text-sm mt-2" placeholder="Optional email" value={flagState.email} onChange={(e) => setFlagState(prev => ({ ...prev, email: e.target.value }))} />
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
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
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
          <Route path="/teams" element={<TeamsPage />} />
          <Route path="/newsletters" element={<NewslettersPage />} />
          {/* Hidden in nav, used only via email links */}
          <Route path="/manage" element={<ManagePage />} />
          <Route path="/unsubscribe" element={<UnsubscribePage />} />
          <Route path="/verify" element={<VerifyPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
