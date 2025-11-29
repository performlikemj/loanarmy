import React, { useState, useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Loader2, Save, ArrowLeft, BarChart2, Layers, FileText, Eye } from 'lucide-react'
import { APIService } from '@/lib/api'
import { mapLoansToPlayerOptions } from './loanPlayerOptions'
import { buildLoanFetchParams } from './loanFetchParams'
import { resolveLatestTeamId } from './teamResolver'
import { PlayerStatsDrawer } from './PlayerStatsDrawer'
import { ContentBlockBuilder } from '@/components/writer/ContentBlockBuilder'
import { CommentaryEditor } from '@/components/CommentaryEditor'

export function WriteupEditor() {
    const navigate = useNavigate()
    const [searchParams] = useSearchParams()
    const editId = searchParams.get('id')

    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState('')

    const [teams, setTeams] = useState([])
    const [players, setPlayers] = useState([])
    const [gameweeks, setGameweeks] = useState([])
    const [loadingPlayers, setLoadingPlayers] = useState(false)

    // Stats Drawer State
    const [isStatsOpen, setIsStatsOpen] = useState(false)
    
    // Editor mode: 'blocks' (new) or 'simple' (legacy)
    const [editorMode, setEditorMode] = useState('blocks')

    // Form State
    const [formData, setFormData] = useState({
        team_id: '',
        commentary_type: 'summary', // summary, intro, player
        player_id: '',
        title: '',
        content: '',  // For legacy simple editor
        structured_blocks: null,  // For new block editor
        is_premium: false,  // Legacy global premium flag
        is_active: true,
        week_start_date: '',
        week_end_date: ''
    })

    useEffect(() => {
        const init = async () => {
            try {
                // Fetch available gameweeks
                const gwData = await APIService.getGameweeks()
                setGameweeks(gwData || [])

                // Fetch assigned teams
                const teamsData = await APIService.getWriterTeams()
                setTeams(teamsData || [])

                // If editing, fetch existing commentary
                if (editId) {
                    const allCommentaries = await APIService.getWriterCommentaries()
                    const existing = allCommentaries.find(c => String(c.id) === String(editId))
                    if (existing) {
                        // Determine editor mode based on content type
                        const hasBlocks = existing.structured_blocks && existing.structured_blocks.length > 0
                        setEditorMode(hasBlocks ? 'blocks' : 'simple')
                        
                        setFormData({
                            id: existing.id,
                            team_id: String(existing.team_id || ''),
                            commentary_type: existing.commentary_type,
                            player_id: existing.player_id ? String(existing.player_id) : '',
                            title: existing.title || '',
                            content: existing.content || '',
                            structured_blocks: existing.structured_blocks || null,
                            is_premium: existing.is_premium || false,
                            is_active: existing.is_active !== false,
                            week_start_date: existing.week_start_date || '',
                            week_end_date: existing.week_end_date || ''
                        })
                    } else {
                        setError('Writeup not found')
                    }
                } else {
                    // New writeup: Auto-select current week
                    if (gwData && gwData.length > 0) {
                        const current = gwData.find(g => g.is_current)
                        if (current) {
                            setFormData(prev => ({
                                ...prev,
                                week_start_date: current.start_date,
                                week_end_date: current.end_date
                            }))
                        }
                    }
                }
            } catch (err) {
                console.error('Failed to init editor', err)
                setError('Failed to load editor data')
            } finally {
                setLoading(false)
            }
        }
        init()
    }, [editId])

    // Fetch players when team changes
    useEffect(() => {
        if (!formData.team_id) {
            setPlayers([])
            return
        }

        const fetchPlayers = async () => {
            setLoadingPlayers(true)
            try {
                const latestTeamId = await resolveLatestTeamId(formData.team_id, APIService)
                const loans = await APIService.getTeamLoans(
                    latestTeamId,
                    buildLoanFetchParams()
                )
                const playerList = mapLoansToPlayerOptions(loans)
                setPlayers(playerList)
            } catch (err) {
                console.error('Failed to fetch players', err)
            } finally {
                setLoadingPlayers(false)
            }
        }
        fetchPlayers()
    }, [formData.team_id])

    const handleChange = (field, value) => {
        setFormData(prev => ({ ...prev, [field]: value }))
    }

    const handleBlocksChange = (blocks) => {
        setFormData(prev => ({ 
            ...prev, 
            structured_blocks: blocks,
            // Clear legacy content when using blocks
            content: '' 
        }))
    }

    const handleSimpleContentChange = (content) => {
        setFormData(prev => ({ 
            ...prev, 
            content,
            // Clear structured blocks when using simple editor
            structured_blocks: null 
        }))
    }

    const weekRange = useMemo(() => ({
        start: formData.week_start_date,
        end: formData.week_end_date
    }), [formData.week_start_date, formData.week_end_date])

    const hasContent = useMemo(() => {
        if (editorMode === 'blocks') {
            return formData.structured_blocks && formData.structured_blocks.length > 0
        }
        return !!formData.content?.trim()
    }, [editorMode, formData.structured_blocks, formData.content])

    const handleSubmit = async (e) => {
        e.preventDefault()
        setSaving(true)
        setError('')

        try {
            // Validation
            if (!formData.team_id && !editId) throw new Error('Please select a team')
            if (!hasContent) throw new Error('Content is required')
            if (formData.commentary_type === 'player' && !formData.player_id) throw new Error('Please select a player')

            // Prepare payload based on editor mode
            const payload = {
                ...formData,
                // Clear the unused content type
                content: editorMode === 'simple' ? formData.content : '',
                structured_blocks: editorMode === 'blocks' ? formData.structured_blocks : null,
            }

            await APIService.saveWriterCommentary(payload)
            navigate('/writer/dashboard')
        } catch (err) {
            setError(err.message || 'Failed to save writeup')
        } finally {
            setSaving(false)
        }
    }

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-gray-50 py-8">
            <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
                <Button variant="ghost" onClick={() => navigate('/writer/dashboard')} className="mb-4">
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back to Dashboard
                </Button>

                <Card>
                    <form onSubmit={handleSubmit}>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle>{editId ? 'Edit Writeup' : 'New Writeup'}</CardTitle>
                                    <CardDescription>Create content for your team report</CardDescription>
                                </div>
                                <Badge variant="outline" className="text-xs">
                                    {editorMode === 'blocks' ? (
                                        <><Layers className="h-3 w-3 mr-1" /> Block Editor</>
                                    ) : (
                                        <><FileText className="h-3 w-3 mr-1" /> Simple Editor</>
                                    )}
                                </Badge>
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            {error && (
                                <div className="p-3 text-sm text-red-500 bg-red-50 rounded border border-red-200">
                                    {error}
                                </div>
                            )}

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {/* Team Selection */}
                                <div className="space-y-2">
                                    <Label htmlFor="team">Team</Label>
                                    <Select
                                        value={formData.team_id}
                                        onValueChange={(val) => handleChange('team_id', val)}
                                        disabled={!!editId}
                                    >
                                        <SelectTrigger>
                                            <SelectValue placeholder="Select team" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {teams.map(t => (
                                                <SelectItem key={t.team_id} value={String(t.team_id)}>
                                                    {t.team_name}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                {/* Type Selection */}
                                <div className="space-y-2">
                                    <Label htmlFor="type">Type</Label>
                                    <Select
                                        value={formData.commentary_type}
                                        onValueChange={(val) => handleChange('commentary_type', val)}
                                    >
                                        <SelectTrigger>
                                            <SelectValue placeholder="Select type" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="summary">Team Summary</SelectItem>
                                            <SelectItem value="intro">Intro/Outro</SelectItem>
                                            <SelectItem value="player">Player Report</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>

                            {/* Player Selection - Required for player type, optional for others in block mode */}
                            {(formData.commentary_type === 'player' || editorMode === 'blocks') && (
                                <div className="space-y-2">
                                    <Label>
                                        Player {formData.commentary_type !== 'player' && <span className="text-gray-400 font-normal">(Optional - for chart data)</span>}
                                    </Label>
                                    <div className="flex gap-2">
                                        <Select
                                            value={formData.player_id || 'none'}
                                            onValueChange={(val) => handleChange('player_id', val === 'none' ? '' : val)}
                                            disabled={loadingPlayers || !formData.team_id}
                                        >
                                            <SelectTrigger className="flex-1">
                                                <SelectValue placeholder={loadingPlayers ? "Loading players..." : "Select player"} />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {formData.commentary_type !== 'player' && (
                                                    <SelectItem value="none">No player (general writeup)</SelectItem>
                                                )}
                                                {players.map(p => (
                                                    <SelectItem key={p.id} value={String(p.id)}>
                                                        {p.name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                        <Button
                                            type="button"
                                            variant="outline"
                                            size="icon"
                                            disabled={!formData.player_id}
                                            onClick={() => setIsStatsOpen(true)}
                                            title="View Player Stats"
                                        >
                                            <BarChart2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                    {editorMode === 'blocks' && formData.commentary_type !== 'player' && (
                                        <p className="text-xs text-gray-500">
                                            Select a player to use their stats in chart blocks
                                        </p>
                                    )}
                                </div>
                            )}

                            {/* Week Selection */}
                            <div className="space-y-2">
                                <Label htmlFor="gameweek">Week</Label>
                                <Select
                                    value={formData.week_start_date && formData.week_end_date ? `${formData.week_start_date}_${formData.week_end_date}` : ''}
                                    onValueChange={(val) => {
                                        const gw = gameweeks.find(g => g.id === val)
                                        if (gw) {
                                            setFormData(prev => ({
                                                ...prev,
                                                week_start_date: gw.start_date,
                                                week_end_date: gw.end_date
                                            }))
                                        }
                                    }}
                                >
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select week" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {gameweeks.map(g => (
                                            <SelectItem key={g.id} value={g.id}>
                                                {g.label} {g.is_current ? '(Current)' : ''}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                <p className="text-xs text-gray-500">
                                    Select the week this report belongs to.
                                </p>
                            </div>

                            {/* Title */}
                            <div className="space-y-2">
                                <Label htmlFor="title">Title (Optional)</Label>
                                <Input
                                    id="title"
                                    value={formData.title}
                                    onChange={(e) => handleChange('title', e.target.value)}
                                    placeholder="e.g. 'Defensive Masterclass'"
                                />
                            </div>

                            {/* Content Editor with Mode Tabs */}
                            <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <Label>Content</Label>
                                    <Tabs value={editorMode} onValueChange={setEditorMode} className="w-auto">
                                        <TabsList className="grid w-auto grid-cols-2">
                                            <TabsTrigger value="blocks" className="text-xs gap-1 px-3">
                                                <Layers className="h-3 w-3" /> Blocks
                                            </TabsTrigger>
                                            <TabsTrigger value="simple" className="text-xs gap-1 px-3">
                                                <FileText className="h-3 w-3" /> Simple
                                            </TabsTrigger>
                                        </TabsList>
                                    </Tabs>
                                </div>

                                {editorMode === 'blocks' ? (
                                    <div className="border rounded-lg p-4 bg-white">
                                        <ContentBlockBuilder
                                            blocks={formData.structured_blocks || []}
                                            onChange={handleBlocksChange}
                                            playerId={formData.player_id || null}
                                            weekRange={weekRange}
                                        />
                                        <p className="text-xs text-gray-500 mt-3">
                                            Build your article with text blocks, charts, and more. Each block can be marked as public or premium.
                                        </p>
                                    </div>
                                ) : (
                                    <div className="space-y-3">
                                        <CommentaryEditor
                                            value={formData.content}
                                            onChange={handleSimpleContentChange}
                                            placeholder="Write your analysis here..."
                                        />
                                        {/* Legacy premium toggle for simple mode */}
                                        <div className="flex items-center space-x-2 pt-2">
                                            <input
                                                type="checkbox"
                                                id="premium"
                                                checked={formData.is_premium}
                                                onChange={(e) => handleChange('is_premium', e.target.checked)}
                                                className="h-4 w-4 rounded border-gray-300"
                                            />
                                            <Label htmlFor="premium" className="text-sm text-gray-600">
                                                Premium Content (Subscribers Only)
                                            </Label>
                                        </div>
                                    </div>
                                )}
                            </div>

                        </CardContent>
                        <CardFooter className="flex justify-between">
                            <Button 
                                type="button" 
                                variant="outline"
                                onClick={() => navigate('/writer/dashboard')}
                            >
                                Cancel
                            </Button>
                            <Button type="submit" disabled={saving || !hasContent}>
                                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                                Save Writeup
                            </Button>
                        </CardFooter>
                    </form>
                </Card>
            </div>

            <PlayerStatsDrawer
                playerId={formData.player_id}
                isOpen={isStatsOpen}
                onClose={setIsStatsOpen}
                playerName={players.find(p => String(p.id) === String(formData.player_id))?.name || 'Player'}
            />
        </div>
    )
}
