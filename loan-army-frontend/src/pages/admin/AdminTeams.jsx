import { useState, useEffect, useCallback, useMemo } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { 
  Loader2, 
  Trash2, 
  CheckCircle, 
  XCircle, 
  Clock, 
  AlertCircle,
  Search,
  RefreshCw,
  Users,
  CheckSquare,
  Square,
  Shield,
  ArrowLeftRight
} from 'lucide-react'
import { APIService } from '@/lib/api'

export function AdminTeams() {
  const [teams, setTeams] = useState([])
  const [trackingRequests, setTrackingRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [requestsLoading, setRequestsLoading] = useState(true)
  const [message, setMessage] = useState(null)
  const [search, setSearch] = useState('')
  const [requestFilter, setRequestFilter] = useState('pending')
  
  // Selection state
  const [selectedTeamIds, setSelectedTeamIds] = useState(new Set())
  const [bulkMode, setBulkMode] = useState('delete') // 'delete' or 'keep'
  
  // Delete team data dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null) // Single team or null for bulk
  const [deletePreview, setDeletePreview] = useState(null)
  const [bulkDeletePreviews, setBulkDeletePreviews] = useState([])
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)

  const loadTeams = useCallback(async () => {
    try {
      setLoading(true)
      const data = await APIService.getTeams({ european_only: 'true' })
      // Sort by name and keep latest season per team
      const teamsArray = Array.isArray(data) ? data : []
      const byApiId = {}
      for (const team of teamsArray) {
        const key = team.team_id
        if (!byApiId[key] || team.season > byApiId[key].season) {
          byApiId[key] = team
        }
      }
      const sorted = Object.values(byApiId).sort((a, b) => a.name.localeCompare(b.name))
      setTeams(sorted)
    } catch (error) {
      console.error('Failed to load teams:', error)
      setMessage({ type: 'error', text: 'Failed to load teams' })
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTrackingRequests = useCallback(async () => {
    try {
      setRequestsLoading(true)
      const data = await APIService.adminListTrackingRequests({ status: requestFilter === 'all' ? '' : requestFilter })
      setTrackingRequests(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Failed to load tracking requests:', error)
      setMessage({ type: 'error', text: 'Failed to load tracking requests' })
    } finally {
      setRequestsLoading(false)
    }
  }, [requestFilter])

  useEffect(() => {
    loadTeams()
  }, [loadTeams])

  useEffect(() => {
    loadTrackingRequests()
  }, [loadTrackingRequests])

  const filteredTeams = useMemo(() => teams.filter(team => 
    team.name.toLowerCase().includes(search.toLowerCase()) ||
    team.league_name?.toLowerCase().includes(search.toLowerCase())
  ), [teams, search])

  const trackedTeams = useMemo(() => filteredTeams.filter(t => t.is_tracked), [filteredTeams])
  const untrackedTeams = useMemo(() => filteredTeams.filter(t => !t.is_tracked), [filteredTeams])

  // Teams that will be deleted based on current selection and mode
  const teamsToDelete = useMemo(() => {
    if (bulkMode === 'delete') {
      return trackedTeams.filter(t => selectedTeamIds.has(t.id))
    } else {
      // 'keep' mode - delete everything NOT selected
      return trackedTeams.filter(t => !selectedTeamIds.has(t.id))
    }
  }, [trackedTeams, selectedTeamIds, bulkMode])

  const teamsToKeep = useMemo(() => {
    if (bulkMode === 'keep') {
      return trackedTeams.filter(t => selectedTeamIds.has(t.id))
    } else {
      return trackedTeams.filter(t => !selectedTeamIds.has(t.id))
    }
  }, [trackedTeams, selectedTeamIds, bulkMode])

  // Selection handlers
  const toggleTeamSelection = (teamId) => {
    setSelectedTeamIds(prev => {
      const next = new Set(prev)
      if (next.has(teamId)) {
        next.delete(teamId)
      } else {
        next.add(teamId)
      }
      return next
    })
  }

  const selectAllTracked = () => {
    setSelectedTeamIds(new Set(trackedTeams.map(t => t.id)))
  }

  const selectNone = () => {
    setSelectedTeamIds(new Set())
  }

  const invertSelection = () => {
    const allIds = new Set(trackedTeams.map(t => t.id))
    const inverted = new Set()
    for (const id of allIds) {
      if (!selectedTeamIds.has(id)) {
        inverted.add(id)
      }
    }
    setSelectedTeamIds(inverted)
  }

  // Single team delete
  const handleDeleteClick = async (team) => {
    setDeleteTarget(team)
    setBulkDeletePreviews([])
    setDeleteDialogOpen(true)
    setDeletePreview(null)
    setPreviewLoading(true)
    
    try {
      const preview = await APIService.adminDeleteTeamData(team.id, true)
      setDeletePreview(preview)
    } catch (error) {
      console.error('Failed to preview delete:', error)
      setMessage({ type: 'error', text: 'Failed to preview deletion' })
    } finally {
      setPreviewLoading(false)
    }
  }

  // Bulk delete preview
  const handleBulkDeleteClick = async () => {
    if (teamsToDelete.length === 0) {
      setMessage({ type: 'error', text: 'No teams selected for deletion' })
      return
    }

    setDeleteTarget(null)
    setDeletePreview(null)
    setDeleteDialogOpen(true)
    setPreviewLoading(true)
    setBulkDeletePreviews([])

    try {
      // Get preview for each team (limit to first 10 for performance)
      const previewTeams = teamsToDelete.slice(0, 10)
      const previews = await Promise.all(
        previewTeams.map(async (team) => {
          try {
            const preview = await APIService.adminDeleteTeamData(team.id, true)
            return { team, preview }
          } catch (err) {
            return { team, preview: null, error: err.message }
          }
        })
      )
      setBulkDeletePreviews(previews)
    } catch (error) {
      console.error('Failed to preview bulk delete:', error)
      setMessage({ type: 'error', text: 'Failed to preview bulk deletion' })
    } finally {
      setPreviewLoading(false)
    }
  }

  const confirmDelete = async () => {
    setDeleteLoading(true)
    
    try {
      if (deleteTarget) {
        // Single delete
        await APIService.adminDeleteTeamData(deleteTarget.id, false)
        setMessage({ type: 'success', text: `Successfully deleted all tracking data for ${deleteTarget.name}` })
      } else {
        // Bulk delete
        let successCount = 0
        let errorCount = 0
        
        for (const team of teamsToDelete) {
          try {
            await APIService.adminDeleteTeamData(team.id, false)
            successCount++
          } catch (err) {
            console.error(`Failed to delete ${team.name}:`, err)
            errorCount++
          }
        }
        
        if (errorCount === 0) {
          setMessage({ type: 'success', text: `Successfully deleted data for ${successCount} teams` })
        } else {
          setMessage({ type: 'warning', text: `Deleted ${successCount} teams, ${errorCount} failed` })
        }
        
        setSelectedTeamIds(new Set())
      }
      
      setDeleteDialogOpen(false)
      setDeleteTarget(null)
      setDeletePreview(null)
      setBulkDeletePreviews([])
      loadTeams()
    } catch (error) {
      console.error('Failed to delete team data:', error)
      setMessage({ type: 'error', text: 'Failed to delete team data' })
    } finally {
      setDeleteLoading(false)
    }
  }

  const handleRequestAction = async (requestId, status, note = '') => {
    try {
      await APIService.adminUpdateTrackingRequest(requestId, { status, note })
      setMessage({ type: 'success', text: `Request ${status}` })
      loadTrackingRequests()
      if (status === 'approved') {
        loadTeams()
      }
    } catch (error) {
      console.error('Failed to update request:', error)
      setMessage({ type: 'error', text: 'Failed to update request' })
    }
  }

  const handleToggleTracking = async (team) => {
    try {
      await APIService.adminUpdateTeamTracking(team.id, !team.is_tracked)
      setMessage({ type: 'success', text: `${team.name} is now ${!team.is_tracked ? 'tracked' : 'untracked'}` })
      loadTeams()
    } catch (error) {
      console.error('Failed to toggle tracking:', error)
      setMessage({ type: 'error', text: 'Failed to update tracking status' })
    }
  }

  // Calculate totals for bulk preview
  const bulkTotals = useMemo(() => {
    const totals = {
      loaned_players: 0,
      newsletters: 0,
      weekly_reports: 0,
      subscriptions: 0,
      commentaries: 0,
      fixture_player_stats: 0
    }
    for (const { preview } of bulkDeletePreviews) {
      if (preview?.deleted) {
        totals.loaned_players += preview.deleted.loaned_players || 0
        totals.newsletters += preview.deleted.newsletters || 0
        totals.weekly_reports += preview.deleted.weekly_reports || 0
        totals.subscriptions += preview.deleted.subscriptions || 0
        totals.commentaries += preview.deleted.commentaries || 0
        totals.fixture_player_stats += preview.deleted.fixture_player_stats || 0
      }
    }
    return totals
  }, [bulkDeletePreviews])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Team Management</h2>
        <p className="text-muted-foreground mt-1">
          Manage team tracking status and data
        </p>
      </div>

      {message && (
        <Alert className={message.type === 'error' ? 'border-red-500' : message.type === 'success' ? 'border-green-500' : 'border-blue-500'}>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="teams">
        <TabsList>
          <TabsTrigger value="teams">
            <Users className="h-4 w-4 mr-2" />
            Teams ({trackedTeams.length} tracked)
          </TabsTrigger>
          <TabsTrigger value="requests">
            <Clock className="h-4 w-4 mr-2" />
            Tracking Requests
            {trackingRequests.filter(r => r.status === 'pending').length > 0 && (
              <Badge variant="destructive" className="ml-2">
                {trackingRequests.filter(r => r.status === 'pending').length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="teams" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Tracked Teams</CardTitle>
                  <CardDescription>
                    Teams currently being tracked for loan player data
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {/* Search and controls */}
              <div className="flex flex-col gap-4 mb-4">
                <div className="flex items-center gap-4">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search teams..."
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                  <Button variant="outline" onClick={loadTeams}>
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Refresh
                  </Button>
                </div>

                {/* Bulk selection controls */}
                {trackedTeams.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 p-3 bg-muted/50 rounded-lg">
                    <span className="text-sm font-medium mr-2">Selection:</span>
                    <Button variant="outline" size="sm" onClick={selectAllTracked}>
                      <CheckSquare className="h-4 w-4 mr-1" />
                      All
                    </Button>
                    <Button variant="outline" size="sm" onClick={selectNone}>
                      <Square className="h-4 w-4 mr-1" />
                      None
                    </Button>
                    <Button variant="outline" size="sm" onClick={invertSelection}>
                      <ArrowLeftRight className="h-4 w-4 mr-1" />
                      Invert
                    </Button>
                    
                    <div className="h-6 w-px bg-border mx-2" />
                    
                    <span className="text-sm text-muted-foreground">
                      {selectedTeamIds.size} selected
                    </span>

                    {selectedTeamIds.size > 0 && (
                      <>
                        <div className="h-6 w-px bg-border mx-2" />
                        
                        <Select value={bulkMode} onValueChange={setBulkMode}>
                          <SelectTrigger className="w-44 h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="delete">
                              <span className="flex items-center gap-2">
                                <Trash2 className="h-3 w-3" />
                                Delete selected
                              </span>
                            </SelectItem>
                            <SelectItem value="keep">
                              <span className="flex items-center gap-2">
                                <Shield className="h-3 w-3" />
                                Keep selected only
                              </span>
                            </SelectItem>
                          </SelectContent>
                        </Select>
                        
                        <Button 
                          variant="destructive" 
                          size="sm"
                          onClick={handleBulkDeleteClick}
                        >
                          <Trash2 className="h-4 w-4 mr-1" />
                          {bulkMode === 'delete' 
                            ? `Delete ${teamsToDelete.length} teams` 
                            : `Delete ${teamsToDelete.length}, keep ${teamsToKeep.length}`
                          }
                        </Button>
                      </>
                    )}
                  </div>
                )}
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              ) : trackedTeams.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">No tracked teams found</p>
              ) : (
                <div className="space-y-2">
                  {trackedTeams.map(team => {
                    const isSelected = selectedTeamIds.has(team.id)
                    const willBeDeleted = teamsToDelete.some(t => t.id === team.id)
                    
                    return (
                      <div 
                        key={team.id} 
                        className={`flex items-center justify-between p-3 border rounded-lg transition-colors ${
                          isSelected 
                            ? willBeDeleted 
                              ? 'bg-red-50 border-red-200' 
                              : 'bg-green-50 border-green-200'
                            : 'hover:bg-muted/50'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <Checkbox
                            checked={isSelected}
                            onCheckedChange={() => toggleTeamSelection(team.id)}
                          />
                          <Avatar className="h-10 w-10">
                            <AvatarImage src={team.logo} alt={team.name} />
                            <AvatarFallback>{team.name.slice(0, 2).toUpperCase()}</AvatarFallback>
                          </Avatar>
                          <div>
                            <p className="font-medium">{team.name}</p>
                            <p className="text-sm text-muted-foreground">
                              {team.league_name || team.country} • {team.current_loaned_out_count} loans
                            </p>
                          </div>
                          {isSelected && selectedTeamIds.size > 0 && (
                            <Badge variant={willBeDeleted ? "destructive" : "default"} className="ml-2">
                              {willBeDeleted ? 'Will be deleted' : 'Will be kept'}
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant="default" className="bg-green-600">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Tracked
                          </Badge>
                          <Button 
                            variant="outline" 
                            size="sm"
                            onClick={() => handleToggleTracking(team)}
                          >
                            Stop Tracking
                          </Button>
                          <Button 
                            variant="destructive" 
                            size="sm"
                            onClick={() => handleDeleteClick(team)}
                          >
                            <Trash2 className="h-4 w-4 mr-1" />
                            Delete
                          </Button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Untracked Teams</CardTitle>
              <CardDescription>
                Teams available but not currently being tracked
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              ) : untrackedTeams.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">All teams are being tracked</p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                  {untrackedTeams.slice(0, 50).map(team => (
                    <div key={team.id} className="flex items-center justify-between p-2 border rounded-lg text-sm">
                      <div className="flex items-center gap-2">
                        <Avatar className="h-8 w-8">
                          <AvatarImage src={team.logo} alt={team.name} />
                          <AvatarFallback className="text-xs">{team.name.slice(0, 2).toUpperCase()}</AvatarFallback>
                        </Avatar>
                        <span className="truncate max-w-[120px]">{team.name}</span>
                      </div>
                      <Button 
                        variant="ghost" 
                        size="sm"
                        onClick={() => handleToggleTracking(team)}
                      >
                        Track
                      </Button>
                    </div>
                  ))}
                </div>
              )}
              {untrackedTeams.length > 50 && (
                <p className="text-center text-muted-foreground mt-4">
                  Showing 50 of {untrackedTeams.length} untracked teams. Use search to find specific teams.
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="requests" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Tracking Requests</CardTitle>
                  <CardDescription>
                    User requests to track new teams
                  </CardDescription>
                </div>
                <Select value={requestFilter} onValueChange={setRequestFilter}>
                  <SelectTrigger className="w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="approved">Approved</SelectItem>
                    <SelectItem value="rejected">Rejected</SelectItem>
                    <SelectItem value="all">All</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent>
              {requestsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              ) : trackingRequests.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">No tracking requests found</p>
              ) : (
                <div className="space-y-3">
                  {trackingRequests.map(req => (
                    <div key={req.id} className="p-4 border rounded-lg">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-center gap-3">
                          {req.team_logo && (
                            <Avatar className="h-12 w-12">
                              <AvatarImage src={req.team_logo} alt={req.team_name} />
                              <AvatarFallback>{req.team_name?.slice(0, 2).toUpperCase()}</AvatarFallback>
                            </Avatar>
                          )}
                          <div>
                            <p className="font-medium">{req.team_name}</p>
                            <p className="text-sm text-muted-foreground">{req.team_league}</p>
                            <p className="text-xs text-muted-foreground mt-1">
                              Requested {new Date(req.created_at).toLocaleDateString()}
                              {req.email && ` by ${req.email}`}
                            </p>
                          </div>
                        </div>
                        <Badge variant={
                          req.status === 'pending' ? 'secondary' :
                          req.status === 'approved' ? 'default' : 'destructive'
                        }>
                          {req.status === 'pending' && <Clock className="h-3 w-3 mr-1" />}
                          {req.status === 'approved' && <CheckCircle className="h-3 w-3 mr-1" />}
                          {req.status === 'rejected' && <XCircle className="h-3 w-3 mr-1" />}
                          {req.status}
                        </Badge>
                      </div>
                      {req.reason && (
                        <p className="text-sm mt-3 p-2 bg-muted rounded">{req.reason}</p>
                      )}
                      {req.admin_note && (
                        <p className="text-sm mt-2 text-muted-foreground italic">
                          Admin note: {req.admin_note}
                        </p>
                      )}
                      {req.status === 'pending' && (
                        <div className="flex gap-2 mt-3">
                          <Button
                            size="sm"
                            onClick={() => handleRequestAction(req.id, 'approved')}
                          >
                            <CheckCircle className="h-4 w-4 mr-1" />
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleRequestAction(req.id, 'rejected')}
                          >
                            <XCircle className="h-4 w-4 mr-1" />
                            Reject
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Delete Team Data Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="sm:max-w-xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-600">
              <Trash2 className="h-5 w-5" />
              {deleteTarget ? 'Delete Team Data' : `Delete Data for ${teamsToDelete.length} Teams`}
            </DialogTitle>
            <DialogDescription>
              {deleteTarget ? (
                <>This will permanently delete all tracking data for <strong>{deleteTarget.name}</strong>.</>
              ) : (
                <>
                  This will permanently delete all tracking data for <strong>{teamsToDelete.length} teams</strong>.
                  {teamsToKeep.length > 0 && (
                    <> <strong>{teamsToKeep.length} teams</strong> will be kept.</>
                  )}
                </>
              )}
              {' '}This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          
          {previewLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin mr-2" />
              <span>Calculating impact...</span>
            </div>
          ) : deleteTarget && deletePreview ? (
            // Single team preview
            <div className="space-y-4 py-4">
              <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                {deleteTarget.logo && (
                  <Avatar className="h-12 w-12">
                    <AvatarImage src={deleteTarget.logo} alt={deleteTarget.name} />
                    <AvatarFallback>{deleteTarget.name?.slice(0, 2).toUpperCase()}</AvatarFallback>
                  </Avatar>
                )}
                <div>
                  <p className="font-medium">{deleteTarget.name}</p>
                  <p className="text-sm text-muted-foreground">{deleteTarget.league_name}</p>
                </div>
              </div>
              
              <div className="border rounded-lg p-4 bg-red-50">
                <p className="font-medium text-red-800 mb-3">The following data will be deleted:</p>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="flex justify-between">
                    <span>Loan Players:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.loaned_players || 0}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Newsletters:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.newsletters || 0}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Weekly Reports:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.weekly_reports || 0}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Subscriptions:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.subscriptions || 0}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Commentaries:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.commentaries || 0}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Fixture Stats:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.fixture_player_stats || 0}</Badge>
                  </div>
                </div>
              </div>
            </div>
          ) : bulkDeletePreviews.length > 0 ? (
            // Bulk preview
            <div className="space-y-4 py-4">
              {/* Teams to keep (if any) */}
              {teamsToKeep.length > 0 && (
                <div className="border rounded-lg p-3 bg-green-50">
                  <p className="font-medium text-green-800 mb-2 flex items-center gap-2">
                    <Shield className="h-4 w-4" />
                    Teams that will be KEPT ({teamsToKeep.length}):
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {teamsToKeep.map(team => (
                      <Badge key={team.id} variant="outline" className="bg-white">
                        {team.name}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Teams to delete */}
              <div className="border rounded-lg p-3 bg-red-50">
                <p className="font-medium text-red-800 mb-2 flex items-center gap-2">
                  <Trash2 className="h-4 w-4" />
                  Teams to DELETE ({teamsToDelete.length}):
                </p>
                <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
                  {teamsToDelete.map(team => (
                    <Badge key={team.id} variant="destructive">
                      {team.name}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Totals */}
              <div className="border rounded-lg p-4 bg-red-50">
                <p className="font-medium text-red-800 mb-3">
                  Total data to be deleted{teamsToDelete.length > 10 && ' (estimated based on first 10 teams)'}:
                </p>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="flex justify-between">
                    <span>Loan Players:</span>
                    <Badge variant="destructive">{bulkTotals.loaned_players}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Newsletters:</span>
                    <Badge variant="destructive">{bulkTotals.newsletters}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Weekly Reports:</span>
                    <Badge variant="destructive">{bulkTotals.weekly_reports}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Subscriptions:</span>
                    <Badge variant="destructive">{bulkTotals.subscriptions}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Commentaries:</span>
                    <Badge variant="destructive">{bulkTotals.commentaries}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Fixture Stats:</span>
                    <Badge variant="destructive">{bulkTotals.fixture_player_stats}</Badge>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button 
              variant="destructive" 
              onClick={confirmDelete}
              disabled={deleteLoading || previewLoading}
            >
              {deleteLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  {deleteTarget ? 'Delete All Data' : `Delete ${teamsToDelete.length} Teams`}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
