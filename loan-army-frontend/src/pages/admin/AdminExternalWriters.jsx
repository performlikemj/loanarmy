import React, { useState, useEffect, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Loader2, Users, Search, UserPlus, Edit, MoreVertical, Building2, MapPin, Plus, X, Mail, ExternalLink, Trash2, CheckCircle, Clock } from 'lucide-react'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Label } from '@/components/ui/label'
import { APIService } from '@/lib/api'
import TeamMultiSelect from '@/components/ui/TeamMultiSelect'

export function AdminExternalWriters() {
    const [writers, setWriters] = useState([])
    const [allTeams, setAllTeams] = useState([])
    const [loanDestinations, setLoanDestinations] = useState([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')

    // Create dialog state
    const [createDialogOpen, setCreateDialogOpen] = useState(false)
    const [creating, setCreating] = useState(false)
    const [createForm, setCreateForm] = useState({
        email: '',
        display_name: '',
        attribution_name: '',
        attribution_url: '',
        bio: '',
        profile_image_url: ''
    })

    // Edit dialog state
    const [editingWriter, setEditingWriter] = useState(null)
    const [editForm, setEditForm] = useState({})
    const [saving, setSaving] = useState(false)

    // Coverage editing state
    const [editingCoverageWriter, setEditingCoverageWriter] = useState(null)
    const [selectedParentClubs, setSelectedParentClubs] = useState([])
    const [selectedLoanTeams, setSelectedLoanTeams] = useState([])
    const [newLoanTeamName, setNewLoanTeamName] = useState('')
    const [loadingAssignments, setLoadingAssignments] = useState(false)
    const [assigning, setAssigning] = useState(false)
    const [coverageTab, setCoverageTab] = useState('parent')

    // Delete confirmation
    const [deleteConfirmWriter, setDeleteConfirmWriter] = useState(null)
    const [deleting, setDeleting] = useState(false)

    // Claim invite state
    const [sendingClaimInvite, setSendingClaimInvite] = useState(null)

    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        try {
            setLoading(true)
            const [writersData, teamsData, loanDestinationsData] = await Promise.all([
                APIService.getEditorManagedWriters(),
                APIService.getTeams(),
                APIService.getLoanDestinations().catch(() => ({ destinations: [] }))
            ])
            setWriters(writersData?.writers || [])
            setAllTeams(teamsData || [])
            setLoanDestinations(loanDestinationsData?.destinations || [])
        } catch (error) {
            console.error('Failed to load data:', error)
        } finally {
            setLoading(false)
        }
    }

    // Stats
    const stats = useMemo(() => {
        const total = writers.length
        const unclaimed = writers.filter(w => w.is_placeholder).length
        const claimed = writers.filter(w => w.is_claimed).length
        return { total, unclaimed, claimed }
    }, [writers])

    // Filtered writers
    const filteredWriters = useMemo(() => {
        if (!searchQuery.trim()) return writers
        const q = searchQuery.toLowerCase()
        return writers.filter(w =>
            w.display_name?.toLowerCase().includes(q) ||
            w.email?.toLowerCase().includes(q) ||
            w.attribution_name?.toLowerCase().includes(q)
        )
    }, [writers, searchQuery])

    // Create writer
    const handleCreate = async () => {
        if (!createForm.email.trim() || !createForm.display_name.trim()) {
            alert('Email and display name are required')
            return
        }

        try {
            setCreating(true)
            await APIService.createPlaceholderWriter(createForm)
            setCreateDialogOpen(false)
            setCreateForm({ email: '', display_name: '', attribution_name: '', attribution_url: '', bio: '', profile_image_url: '' })
            loadData()
        } catch (error) {
            console.error('Failed to create writer:', error)
            alert(error.message || 'Failed to create writer')
        } finally {
            setCreating(false)
        }
    }

    // Open edit dialog
    const handleOpenEdit = (writer) => {
        setEditingWriter(writer)
        setEditForm({
            display_name: writer.display_name || '',
            attribution_name: writer.attribution_name || '',
            attribution_url: writer.attribution_url || '',
            bio: writer.bio || '',
            profile_image_url: writer.profile_image_url || ''
        })
    }

    // Save edit
    const handleSaveEdit = async () => {
        if (!editingWriter) return

        try {
            setSaving(true)
            await APIService.updatePlaceholderWriter(editingWriter.id, editForm)
            setEditingWriter(null)
            loadData()
        } catch (error) {
            console.error('Failed to update writer:', error)
            alert(error.message || 'Failed to update writer')
        } finally {
            setSaving(false)
        }
    }

    // Open coverage editing
    const handleOpenCoverage = async (writer) => {
        setEditingCoverageWriter(writer)
        setCoverageTab('parent')
        setLoadingAssignments(true)

        try {
            // Load existing assignments from writer data
            const parentTeamIds = (writer.assigned_teams || []).map(t => t.team_id)
            setSelectedParentClubs(parentTeamIds)

            const loanTeams = (writer.loan_team_assignments || []).map(lt => ({
                loan_team_id: lt.loan_team_id,
                loan_team_name: lt.loan_team_name
            }))
            setSelectedLoanTeams(loanTeams)
        } finally {
            setLoadingAssignments(false)
        }
    }

    // Save coverage
    const handleSaveCoverage = async () => {
        if (!editingCoverageWriter) return

        try {
            setAssigning(true)

            // Save both parent clubs and loan teams
            await Promise.all([
                APIService.editorAssignTeams(editingCoverageWriter.id, selectedParentClubs),
                APIService.editorAssignLoanTeams(editingCoverageWriter.id, selectedLoanTeams)
            ])

            setEditingCoverageWriter(null)
            loadData()
        } catch (error) {
            console.error('Failed to save coverage:', error)
            alert(error.message || 'Failed to save coverage')
        } finally {
            setAssigning(false)
        }
    }

    // Add loan team
    const handleAddLoanTeam = () => {
        const name = newLoanTeamName.trim()
        if (!name) return

        // Check for duplicate
        if (selectedLoanTeams.some(lt => lt.loan_team_name.toLowerCase() === name.toLowerCase())) {
            return
        }

        // Check if it matches a known destination
        const match = loanDestinations.find(d =>
            d.loan_team_name?.toLowerCase() === name.toLowerCase()
        )

        setSelectedLoanTeams([
            ...selectedLoanTeams,
            {
                loan_team_id: match?.loan_team_id || null,
                loan_team_name: match?.loan_team_name || name
            }
        ])
        setNewLoanTeamName('')
    }

    // Remove loan team
    const handleRemoveLoanTeam = (index) => {
        setSelectedLoanTeams(selectedLoanTeams.filter((_, i) => i !== index))
    }

    // Delete writer
    const handleDelete = async () => {
        if (!deleteConfirmWriter) return

        try {
            setDeleting(true)
            await APIService.deletePlaceholderWriter(deleteConfirmWriter.id)
            setDeleteConfirmWriter(null)
            loadData()
        } catch (error) {
            console.error('Failed to delete writer:', error)
            alert(error.message || 'Failed to delete writer')
        } finally {
            setDeleting(false)
        }
    }

    // Send claim invite
    const handleSendClaimInvite = async (writer) => {
        try {
            setSendingClaimInvite(writer.id)
            const result = await APIService.sendClaimInvite(writer.id)

            if (result.warning) {
                // Email failed but token was generated
                alert(`${result.warning}\n\nClaim URL: ${result.claim_url}`)
            } else {
                alert(`Claim invitation sent to ${result.email}`)
            }
        } catch (error) {
            console.error('Failed to send claim invite:', error)
            alert(error.message || 'Failed to send claim invitation')
        } finally {
            setSendingClaimInvite(null)
        }
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center p-8">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">External Writers</h1>
                    <p className="text-muted-foreground">
                        Manage placeholder accounts for external contributors
                    </p>
                </div>
                <Button onClick={() => setCreateDialogOpen(true)}>
                    <UserPlus className="h-4 w-4 mr-2" />
                    Add External Writer
                </Button>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Total Writers</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.total}</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Unclaimed</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-amber-600">{stats.unclaimed}</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">Claimed</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-green-600">{stats.claimed}</div>
                    </CardContent>
                </Card>
            </div>

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                    placeholder="Search writers..."
                    className="pl-10"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                />
            </div>

            {/* Writers List */}
            <Card>
                <CardHeader>
                    <CardTitle>Writers</CardTitle>
                    <CardDescription>
                        External writers you've added to the platform
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {filteredWriters.length === 0 ? (
                        <p className="text-muted-foreground text-center py-8">
                            No external writers found. Click "Add External Writer" to create one.
                        </p>
                    ) : (
                        <div className="space-y-4">
                            {filteredWriters.map((writer) => (
                                <div
                                    key={writer.id}
                                    className="flex items-center justify-between p-4 border rounded-lg"
                                >
                                    <div className="flex items-center gap-4">
                                        <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
                                            {writer.profile_image_url ? (
                                                <img
                                                    src={writer.profile_image_url}
                                                    alt=""
                                                    className="w-10 h-10 rounded-full object-cover"
                                                />
                                            ) : (
                                                <Users className="h-5 w-5 text-muted-foreground" />
                                            )}
                                        </div>
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <span className="font-medium">{writer.display_name}</span>
                                                {writer.is_placeholder && (
                                                    <Badge variant="outline" className="text-amber-600 border-amber-300">
                                                        <Clock className="h-3 w-3 mr-1" />
                                                        Unclaimed
                                                    </Badge>
                                                )}
                                                {writer.is_claimed && (
                                                    <Badge variant="outline" className="text-green-600 border-green-300">
                                                        <CheckCircle className="h-3 w-3 mr-1" />
                                                        Claimed
                                                    </Badge>
                                                )}
                                            </div>
                                            <div className="text-sm text-muted-foreground">{writer.email}</div>
                                            {writer.attribution_name && (
                                                <div className="text-sm text-muted-foreground flex items-center gap-1">
                                                    <ExternalLink className="h-3 w-3" />
                                                    {writer.attribution_name}
                                                </div>
                                            )}
                                            {(writer.assigned_teams?.length > 0 || writer.loan_team_assignments?.length > 0) && (
                                                <div className="flex flex-wrap gap-1 mt-1">
                                                    {writer.assigned_teams?.map(team => (
                                                        <Badge key={team.id} variant="secondary" className="text-xs">
                                                            <Building2 className="h-3 w-3 mr-1" />
                                                            {team.name}
                                                        </Badge>
                                                    ))}
                                                    {writer.loan_team_assignments?.map(lt => (
                                                        <Badge key={lt.id} variant="outline" className="text-xs">
                                                            <MapPin className="h-3 w-3 mr-1" />
                                                            {lt.loan_team_name}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="ghost" size="icon">
                                                <MoreVertical className="h-4 w-4" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                                            <DropdownMenuSeparator />
                                            <DropdownMenuItem onClick={() => handleOpenEdit(writer)}>
                                                <Edit className="h-4 w-4 mr-2" />
                                                Edit Profile
                                            </DropdownMenuItem>
                                            <DropdownMenuItem onClick={() => handleOpenCoverage(writer)}>
                                                <Building2 className="h-4 w-4 mr-2" />
                                                Edit Coverage
                                            </DropdownMenuItem>
                                            {writer.is_placeholder && (
                                                <>
                                                    <DropdownMenuSeparator />
                                                    <DropdownMenuItem
                                                        onClick={() => handleSendClaimInvite(writer)}
                                                        disabled={sendingClaimInvite === writer.id}
                                                    >
                                                        <Mail className="h-4 w-4 mr-2" />
                                                        {sendingClaimInvite === writer.id ? 'Sending...' : 'Send Claim Invite'}
                                                    </DropdownMenuItem>
                                                    <DropdownMenuSeparator />
                                                    <DropdownMenuItem
                                                        className="text-destructive"
                                                        onClick={() => setDeleteConfirmWriter(writer)}
                                                    >
                                                        <Trash2 className="h-4 w-4 mr-2" />
                                                        Delete
                                                    </DropdownMenuItem>
                                                </>
                                            )}
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Create Writer Dialog */}
            <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Add External Writer</DialogTitle>
                        <DialogDescription>
                            Create a placeholder account for an external contributor.
                            They can claim it later if they want direct platform access.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="email">Email *</Label>
                            <Input
                                id="email"
                                type="email"
                                placeholder="writer@example.com"
                                value={createForm.email}
                                onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="display_name">Display Name *</Label>
                            <Input
                                id="display_name"
                                placeholder="John Smith"
                                value={createForm.display_name}
                                onChange={(e) => setCreateForm({ ...createForm, display_name: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="attribution_name">Attribution Name</Label>
                            <Input
                                id="attribution_name"
                                placeholder="The Leyton Orienter"
                                value={createForm.attribution_name}
                                onChange={(e) => setCreateForm({ ...createForm, attribution_name: e.target.value })}
                            />
                            <p className="text-xs text-muted-foreground">
                                Publication or organization name for attribution
                            </p>
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="attribution_url">Attribution URL</Label>
                            <Input
                                id="attribution_url"
                                placeholder="https://leytonorienter.co.uk"
                                value={createForm.attribution_url}
                                onChange={(e) => setCreateForm({ ...createForm, attribution_url: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="bio">Bio</Label>
                            <Textarea
                                id="bio"
                                placeholder="Brief bio about the writer..."
                                value={createForm.bio}
                                onChange={(e) => setCreateForm({ ...createForm, bio: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="profile_image_url">Profile Image URL</Label>
                            <Input
                                id="profile_image_url"
                                placeholder="https://example.com/photo.jpg"
                                value={createForm.profile_image_url}
                                onChange={(e) => setCreateForm({ ...createForm, profile_image_url: e.target.value })}
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={handleCreate} disabled={creating}>
                            {creating && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Create Writer
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Edit Writer Dialog */}
            <Dialog open={!!editingWriter} onOpenChange={() => setEditingWriter(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Edit Writer Profile</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="edit_display_name">Display Name</Label>
                            <Input
                                id="edit_display_name"
                                value={editForm.display_name || ''}
                                onChange={(e) => setEditForm({ ...editForm, display_name: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="edit_attribution_name">Attribution Name</Label>
                            <Input
                                id="edit_attribution_name"
                                value={editForm.attribution_name || ''}
                                onChange={(e) => setEditForm({ ...editForm, attribution_name: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="edit_attribution_url">Attribution URL</Label>
                            <Input
                                id="edit_attribution_url"
                                value={editForm.attribution_url || ''}
                                onChange={(e) => setEditForm({ ...editForm, attribution_url: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="edit_bio">Bio</Label>
                            <Textarea
                                id="edit_bio"
                                value={editForm.bio || ''}
                                onChange={(e) => setEditForm({ ...editForm, bio: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="edit_profile_image_url">Profile Image URL</Label>
                            <Input
                                id="edit_profile_image_url"
                                value={editForm.profile_image_url || ''}
                                onChange={(e) => setEditForm({ ...editForm, profile_image_url: e.target.value })}
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setEditingWriter(null)}>
                            Cancel
                        </Button>
                        <Button onClick={handleSaveEdit} disabled={saving}>
                            {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Save Changes
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Coverage Dialog */}
            <Dialog open={!!editingCoverageWriter} onOpenChange={() => setEditingCoverageWriter(null)}>
                <DialogContent className="max-w-2xl">
                    <DialogHeader>
                        <DialogTitle>Edit Coverage for {editingCoverageWriter?.display_name}</DialogTitle>
                        <DialogDescription>
                            Assign teams this writer can cover
                        </DialogDescription>
                    </DialogHeader>

                    {loadingAssignments ? (
                        <div className="flex justify-center py-8">
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : (
                        <Tabs value={coverageTab} onValueChange={setCoverageTab}>
                            <TabsList className="grid w-full grid-cols-2">
                                <TabsTrigger value="parent">
                                    <Building2 className="h-4 w-4 mr-2" />
                                    Parent Clubs
                                </TabsTrigger>
                                <TabsTrigger value="loan">
                                    <MapPin className="h-4 w-4 mr-2" />
                                    Loan Teams
                                </TabsTrigger>
                            </TabsList>

                            <TabsContent value="parent" className="py-4">
                                <p className="text-sm text-muted-foreground mb-4">
                                    Select parent clubs whose loaned players this writer can cover.
                                </p>
                                <TeamMultiSelect
                                    teams={allTeams}
                                    selectedIds={selectedParentClubs}
                                    onChange={setSelectedParentClubs}
                                />
                            </TabsContent>

                            <TabsContent value="loan" className="py-4">
                                <p className="text-sm text-muted-foreground mb-4">
                                    Add loan destination teams this writer watches and covers.
                                </p>
                                <div className="space-y-4">
                                    <div className="flex gap-2">
                                        <Input
                                            placeholder="Add team name..."
                                            value={newLoanTeamName}
                                            onChange={(e) => setNewLoanTeamName(e.target.value)}
                                            onKeyDown={(e) => e.key === 'Enter' && handleAddLoanTeam()}
                                            list="loan-destinations"
                                        />
                                        <datalist id="loan-destinations">
                                            {loanDestinations.map((d) => (
                                                <option key={d.loan_team_name} value={d.loan_team_name} />
                                            ))}
                                        </datalist>
                                        <Button onClick={handleAddLoanTeam} size="icon">
                                            <Plus className="h-4 w-4" />
                                        </Button>
                                    </div>

                                    <div className="flex flex-wrap gap-2">
                                        {selectedLoanTeams.map((lt, index) => (
                                            <Badge key={index} variant="secondary" className="pr-1">
                                                {lt.loan_team_name}
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-4 w-4 ml-1 hover:bg-transparent"
                                                    onClick={() => handleRemoveLoanTeam(index)}
                                                >
                                                    <X className="h-3 w-3" />
                                                </Button>
                                            </Badge>
                                        ))}
                                        {selectedLoanTeams.length === 0 && (
                                            <p className="text-sm text-muted-foreground">No loan teams assigned</p>
                                        )}
                                    </div>
                                </div>
                            </TabsContent>
                        </Tabs>
                    )}

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setEditingCoverageWriter(null)}>
                            Cancel
                        </Button>
                        <Button onClick={handleSaveCoverage} disabled={assigning}>
                            {assigning && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Save Coverage
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Delete Confirmation Dialog */}
            <Dialog open={!!deleteConfirmWriter} onOpenChange={() => setDeleteConfirmWriter(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete Writer</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to delete {deleteConfirmWriter?.display_name}?
                            This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteConfirmWriter(null)}>
                            Cancel
                        </Button>
                        <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
                            {deleting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Delete
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}

export default AdminExternalWriters
