import { useState, useEffect, useCallback } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { AlertCircle, CheckCircle2, Loader2, Plus, Trash2, ExternalLink, Settings2 } from 'lucide-react'
import TeamSelect from '@/components/ui/TeamSelect.jsx'

export function AdminReddit() {
    // State
    const [subreddits, setSubreddits] = useState([])
    const [loading, setLoading] = useState(false)
    const [message, setMessage] = useState(null)
    const [teams, setTeams] = useState([])
    
    // Reddit status
    const [redditStatus, setRedditStatus] = useState(null)
    const [statusLoading, setStatusLoading] = useState(true)
    
    // Add subreddit dialog
    const [addDialogOpen, setAddDialogOpen] = useState(false)
    const [addLoading, setAddLoading] = useState(false)
    const [newSubreddit, setNewSubreddit] = useState({
        team_id: '',
        subreddit_name: '',
        post_format: 'full'
    })
    
    // Delete confirmation
    const [deleteTarget, setDeleteTarget] = useState(null)
    const [deleteLoading, setDeleteLoading] = useState(false)

    // Load Reddit status
    useEffect(() => {
        const checkStatus = async () => {
            try {
                setStatusLoading(true)
                const status = await APIService.adminRedditStatus()
                setRedditStatus(status)
            } catch (err) {
                console.error('Failed to check Reddit status', err)
                setRedditStatus({ configured: false, authenticated: false, message: 'Failed to check status' })
            } finally {
                setStatusLoading(false)
            }
        }
        checkStatus()
    }, [])

    // Load teams
    useEffect(() => {
        const loadTeams = async () => {
            try {
                const teamsData = await APIService.getTeams()
                // Filter to only tracked teams
                const tracked = (teamsData || []).filter(t => t.is_tracked)
                setTeams(tracked)
            } catch (error) {
                console.error('Failed to load teams', error)
            }
        }
        loadTeams()
    }, [])

    // Load subreddits
    const loadSubreddits = useCallback(async () => {
        setLoading(true)
        try {
            const data = await APIService.adminTeamSubredditsList()
            setSubreddits(data?.subreddits || [])
        } catch (error) {
            console.error('Failed to load subreddits', error)
            setMessage({ type: 'error', text: 'Failed to load subreddit mappings' })
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        loadSubreddits()
    }, [loadSubreddits])

    // Add subreddit
    const handleAddSubreddit = async () => {
        if (!newSubreddit.team_id || !newSubreddit.subreddit_name.trim()) {
            setMessage({ type: 'error', text: 'Please select a team and enter a subreddit name' })
            return
        }

        setAddLoading(true)
        try {
            await APIService.adminTeamSubredditCreate({
                team_id: parseInt(newSubreddit.team_id),
                subreddit_name: newSubreddit.subreddit_name.trim().replace(/^r\//, ''),
                post_format: newSubreddit.post_format
            })
            setMessage({ type: 'success', text: `Added r/${newSubreddit.subreddit_name.replace(/^r\//, '')}` })
            setAddDialogOpen(false)
            setNewSubreddit({ team_id: '', subreddit_name: '', post_format: 'full' })
            await loadSubreddits()
        } catch (error) {
            setMessage({ type: 'error', text: error.message || 'Failed to add subreddit' })
        } finally {
            setAddLoading(false)
        }
    }

    // Toggle active status
    const toggleActive = async (subreddit) => {
        try {
            await APIService.adminTeamSubredditUpdate(subreddit.id, {
                is_active: !subreddit.is_active
            })
            setMessage({ 
                type: 'success', 
                text: `r/${subreddit.subreddit_name} ${!subreddit.is_active ? 'activated' : 'deactivated'}` 
            })
            await loadSubreddits()
        } catch (error) {
            setMessage({ type: 'error', text: error.message || 'Failed to update subreddit' })
        }
    }

    // Update post format
    const updateFormat = async (subreddit, format) => {
        try {
            await APIService.adminTeamSubredditUpdate(subreddit.id, {
                post_format: format
            })
            await loadSubreddits()
        } catch (error) {
            setMessage({ type: 'error', text: error.message || 'Failed to update format' })
        }
    }

    // Delete subreddit
    const confirmDelete = (subreddit) => {
        setDeleteTarget(subreddit)
    }

    const executeDelete = async () => {
        if (!deleteTarget) return

        setDeleteLoading(true)
        try {
            await APIService.adminTeamSubredditDelete(deleteTarget.id)
            setMessage({ type: 'success', text: `Deleted r/${deleteTarget.subreddit_name}` })
            setDeleteTarget(null)
            await loadSubreddits()
        } catch (error) {
            setMessage({ type: 'error', text: error.message || 'Failed to delete subreddit' })
        } finally {
            setDeleteLoading(false)
        }
    }

    // Group subreddits by team
    const groupedSubreddits = subreddits.reduce((acc, sub) => {
        const teamName = sub.team_name || 'Unknown Team'
        if (!acc[teamName]) {
            acc[teamName] = []
        }
        acc[teamName].push(sub)
        return acc
    }, {})

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Reddit Integration</h2>
                <p className="text-muted-foreground mt-1">Manage subreddit mappings for automatic newsletter posting</p>
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

            {/* Reddit Connection Status */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Settings2 className="h-5 w-5" />
                        Connection Status
                    </CardTitle>
                    <CardDescription>Reddit API authentication status</CardDescription>
                </CardHeader>
                <CardContent>
                    {statusLoading ? (
                        <div className="flex items-center gap-2">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span className="text-sm text-muted-foreground">Checking connection...</span>
                        </div>
                    ) : redditStatus?.configured && redditStatus?.authenticated ? (
                        <div className="flex items-center gap-3">
                            <Badge className="bg-green-100 text-green-800 hover:bg-green-100">
                                <CheckCircle2 className="h-3 w-3 mr-1" />
                                Connected
                            </Badge>
                            <span className="text-sm text-muted-foreground">
                                Authenticated as <strong className="text-foreground">u/{redditStatus.username}</strong>
                            </span>
                        </div>
                    ) : redditStatus?.configured ? (
                        <div className="flex items-center gap-3">
                            <Badge variant="destructive">
                                <AlertCircle className="h-3 w-3 mr-1" />
                                Auth Failed
                            </Badge>
                            <span className="text-sm text-muted-foreground">
                                {redditStatus.message || 'Authentication failed'}
                            </span>
                        </div>
                    ) : (
                        <div className="flex items-center gap-3">
                            <Badge variant="outline">
                                Not Configured
                            </Badge>
                            <span className="text-sm text-muted-foreground">
                                Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD environment variables
                            </span>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Subreddit Mappings */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle>Team Subreddit Mappings</CardTitle>
                            <CardDescription>
                                Configure which subreddits receive newsletter posts for each team
                            </CardDescription>
                        </div>
                        <Button onClick={() => setAddDialogOpen(true)} disabled={!redditStatus?.configured}>
                            <Plus className="h-4 w-4 mr-2" />
                            Add Subreddit
                        </Button>
                    </div>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" />
                            Loading subreddit mappings...
                        </div>
                    ) : Object.keys(groupedSubreddits).length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <Settings2 className="h-12 w-12 mx-auto mb-3 opacity-50" />
                            <p>No subreddit mappings configured</p>
                            <p className="text-sm mt-1">Add subreddits to enable Reddit posting for teams</p>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {Object.entries(groupedSubreddits).sort((a, b) => a[0].localeCompare(b[0])).map(([teamName, teamSubs]) => (
                                <div key={teamName} className="border rounded-lg p-4">
                                    <h4 className="font-semibold mb-3">{teamName}</h4>
                                    <div className="space-y-2">
                                        {teamSubs.map((sub) => (
                                            <div key={sub.id} className="flex items-center justify-between gap-4 py-2 px-3 bg-muted/50 rounded-md">
                                                <div className="flex items-center gap-3">
                                                    <Badge variant={sub.is_active ? 'default' : 'secondary'}>
                                                        {sub.is_active ? 'Active' : 'Inactive'}
                                                    </Badge>
                                                    <a 
                                                        href={sub.subreddit_url} 
                                                        target="_blank" 
                                                        rel="noopener noreferrer"
                                                        className="text-orange-600 hover:text-orange-700 font-medium flex items-center gap-1"
                                                    >
                                                        r/{sub.subreddit_name}
                                                        <ExternalLink className="h-3 w-3" />
                                                    </a>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <Select
                                                        value={sub.post_format}
                                                        onValueChange={(value) => updateFormat(sub, value)}
                                                    >
                                                        <SelectTrigger className="w-28 h-8">
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            <SelectItem value="full">Full</SelectItem>
                                                            <SelectItem value="compact">Compact</SelectItem>
                                                        </SelectContent>
                                                    </Select>
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        onClick={() => toggleActive(sub)}
                                                    >
                                                        {sub.is_active ? 'Disable' : 'Enable'}
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="destructive"
                                                        onClick={() => confirmDelete(sub)}
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
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

            {/* Add Subreddit Dialog */}
            <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Add Subreddit Mapping</DialogTitle>
                        <DialogDescription>
                            Configure a subreddit to receive newsletter posts for a team
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label>Team</Label>
                            <TeamSelect
                                teams={teams}
                                value={newSubreddit.team_id}
                                onChange={(id) => setNewSubreddit({ ...newSubreddit, team_id: id })}
                                placeholder="Select team..."
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="subreddit-name">Subreddit Name</Label>
                            <div className="flex items-center gap-2">
                                <span className="text-muted-foreground">r/</span>
                                <Input
                                    id="subreddit-name"
                                    value={newSubreddit.subreddit_name}
                                    onChange={(e) => setNewSubreddit({ ...newSubreddit, subreddit_name: e.target.value })}
                                    placeholder="reddevils"
                                />
                            </div>
                            <p className="text-xs text-muted-foreground">
                                Enter the subreddit name without the r/ prefix
                            </p>
                        </div>
                        <div className="space-y-2">
                            <Label>Post Format</Label>
                            <Select
                                value={newSubreddit.post_format}
                                onValueChange={(value) => setNewSubreddit({ ...newSubreddit, post_format: value })}
                            >
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="full">Full (detailed stats tables)</SelectItem>
                                    <SelectItem value="compact">Compact (summary table)</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setAddDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleAddSubreddit} disabled={addLoading}>
                            {addLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Add Subreddit
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Delete Confirmation Dialog */}
            <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete Subreddit Mapping?</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to remove <strong>r/{deleteTarget?.subreddit_name}</strong> from {deleteTarget?.team_name}?
                            This will not affect any posts already made to Reddit.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteTarget(null)}>
                            Cancel
                        </Button>
                        <Button variant="destructive" onClick={executeDelete} disabled={deleteLoading}>
                            {deleteLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Delete
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}









