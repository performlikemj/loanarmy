import React, { useState, useEffect, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Loader2, Users, Search, ShieldCheck, Shield, UserPlus, Edit, MoreVertical, Building2, MapPin, Plus, X } from 'lucide-react'
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

export function AdminUsers() {
    const [users, setUsers] = useState([])
    const [allTeams, setAllTeams] = useState([])
    const [loanDestinations, setLoanDestinations] = useState([])
    const [journalistStats, setJournalistStats] = useState(null)
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')

    // Dialog states
    const [inviteDialogOpen, setInviteDialogOpen] = useState(false)
    const [inviteEmail, setInviteEmail] = useState('')
    const [inviting, setInviting] = useState(false)

    // Coverage editing state
    const [editingCoverageUser, setEditingCoverageUser] = useState(null)
    const [selectedParentClubs, setSelectedParentClubs] = useState([])
    const [selectedLoanTeams, setSelectedLoanTeams] = useState([]) // [{loan_team_id: number|null, loan_team_name: string}]
    const [newLoanTeamName, setNewLoanTeamName] = useState('')
    const [loadingAssignments, setLoadingAssignments] = useState(false)
    const [assigning, setAssigning] = useState(false)
    const [coverageTab, setCoverageTab] = useState('parent')

    const [confirmRoleChangeUser, setConfirmRoleChangeUser] = useState(null)
    const [togglingRole, setTogglingRole] = useState(false)

    // Editor role toggle
    const [confirmEditorChangeUser, setConfirmEditorChangeUser] = useState(null)
    const [togglingEditor, setTogglingEditor] = useState(false)

    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        try {
            setLoading(true)
            const [usersData, teamsData, statsData, loanDestinationsData] = await Promise.all([
                APIService.adminGetUsers(),
                APIService.getTeams(),
                APIService.adminGetJournalistStats().catch(() => null),
                APIService.getLoanDestinations().catch(() => ({ destinations: [] }))
            ])
            setUsers(usersData || [])
            setAllTeams(teamsData || [])
            setJournalistStats(statsData)
            setLoanDestinations(loanDestinationsData?.destinations || [])
        } catch (error) {
            console.error('Failed to load data:', error)
        } finally {
            setLoading(false)
        }
    }

    const handleInviteJournalist = async () => {
        if (!inviteEmail.trim()) return

        try {
            setInviting(true)
            await APIService.adminInviteJournalist(inviteEmail)
            setInviteEmail('')
            setInviteDialogOpen(false)
            loadData() // Reload list
        } catch (error) {
            console.error('Failed to invite journalist:', error)
            alert(error.message || 'Failed to invite journalist')
        } finally {
            setInviting(false)
        }
    }

    const handleToggleJournalist = (user) => {
        setConfirmRoleChangeUser(user)
    }

    const confirmToggleJournalist = async () => {
        if (!confirmRoleChangeUser) return

        try {
            setTogglingRole(true)
            await APIService.adminUpdateUserRole(confirmRoleChangeUser.id, !confirmRoleChangeUser.is_journalist)
            setConfirmRoleChangeUser(null)
            loadData()
        } catch (error) {
            console.error('Failed to update role:', error)
            alert(error.message || 'Failed to update user role')
        } finally {
            setTogglingRole(false)
        }
    }

    const handleToggleEditor = (user) => {
        setConfirmEditorChangeUser(user)
    }

    const confirmToggleEditor = async () => {
        if (!confirmEditorChangeUser) return

        try {
            setTogglingEditor(true)
            await APIService.adminUpdateEditorRole(confirmEditorChangeUser.id, !confirmEditorChangeUser.is_editor)
            setConfirmEditorChangeUser(null)
            loadData()
        } catch (error) {
            console.error('Failed to update editor role:', error)
            alert(error.message || 'Failed to update editor role')
        } finally {
            setTogglingEditor(false)
        }
    }

    const handleEditCoverage = async (user) => {
        setEditingCoverageUser(user)
        setCoverageTab('parent')
        setNewLoanTeamName('')

        // Load existing assignments
        try {
            setLoadingAssignments(true)
            const assignments = await APIService.adminGetJournalistAllAssignments(user.id)

            // Set parent clubs - extract team_id (API ID) from each assignment
            const parentClubIds = (assignments.parent_club_assignments || []).map(a => {
                // Try to find the team in allTeams to get its API team_id
                const team = allTeams.find(t => t.id === a.team_id)
                return team?.team_id || a.team_id
            }).filter(Boolean)
            setSelectedParentClubs(parentClubIds)

            // Set loan teams
            const loanTeams = (assignments.loan_team_assignments || []).map(a => ({
                loan_team_id: a.loan_team_id,
                loan_team_name: a.loan_team_name
            }))
            setSelectedLoanTeams(loanTeams)
        } catch (error) {
            console.error('Failed to load assignments:', error)
            // Fall back to user.reporting data
            const currentTeamIds = user.reporting?.map(t => t.team_id) || []
            setSelectedParentClubs(currentTeamIds)
            setSelectedLoanTeams([])
        } finally {
            setLoadingAssignments(false)
        }
    }

    const loanTeamOptions = useMemo(() => {
        const map = new Map()

        loanDestinations.forEach(dest => {
            const name = (dest?.name || '').trim()
            if (!name) return
            const key = name.toLowerCase()
            map.set(key, { name, loan_team_id: dest?.team_id ?? null })
        })

        allTeams.forEach(team => {
            const name = (team?.name || '').trim()
            if (!name) return
            const key = name.toLowerCase()
            if (!map.has(key)) {
                map.set(key, { name, loan_team_id: team?.id ?? null })
                return
            }
            const existing = map.get(key)
            if (existing && !existing.loan_team_id && team?.id) {
                map.set(key, { ...existing, loan_team_id: team.id })
            }
        })

        return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name))
    }, [allTeams, loanDestinations])

    const handleAddLoanTeam = () => {
        const name = newLoanTeamName.trim()
        if (!name) return

        // Check if already exists
        if (selectedLoanTeams.some(lt => lt.loan_team_name.toLowerCase() === name.toLowerCase())) {
            alert('This loan team is already added')
            return
        }

        // Check if it's a known team
        const knownTeam = loanTeamOptions.find(t => t.name.toLowerCase() === name.toLowerCase())

        setSelectedLoanTeams(prev => [...prev, {
            loan_team_id: knownTeam?.loan_team_id || null,
            loan_team_name: knownTeam?.name || name
        }])
        setNewLoanTeamName('')
    }

    const handleRemoveLoanTeam = (teamName) => {
        setSelectedLoanTeams(prev => prev.filter(lt => lt.loan_team_name !== teamName))
    }

    const handleSaveCoverage = async () => {
        if (!editingCoverageUser) return

        try {
            setAssigning(true)

            // Save both types in parallel
            await Promise.all([
                APIService.adminUpdateJournalistTeams(editingCoverageUser.id, selectedParentClubs),
                APIService.adminAssignLoanTeams(editingCoverageUser.id, selectedLoanTeams)
            ])

            setEditingCoverageUser(null)
            setSelectedParentClubs([])
            setSelectedLoanTeams([])
            loadData() // Reload list
        } catch (error) {
            console.error('Failed to update coverage:', error)
            alert(error.message || 'Failed to update coverage assignments')
        } finally {
            setAssigning(false)
        }
    }

    const handleCloseCoverageDialog = () => {
        setEditingCoverageUser(null)
        setSelectedParentClubs([])
        setSelectedLoanTeams([])
        setNewLoanTeamName('')
    }


    const filteredUsers = users.filter(user => {
        const query = searchQuery.toLowerCase()
        return (
            (user.display_name || '').toLowerCase().includes(query) ||
            (user.email || '').toLowerCase().includes(query)
        )
    })

    if (loading) {
        return (
            <div className="flex justify-center items-center min-h-screen">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between lg:items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Users</h2>
                    <p className="text-muted-foreground">Manage all registered users and journalists</p>
                </div>
                <Button className="w-full sm:w-auto" onClick={() => setInviteDialogOpen(true)}>
                    <UserPlus className="mr-2 h-4 w-4" /> Invite User
                </Button>
            </div>

            {/* Journalist Analytics Section */}
            {journalistStats && journalistStats.journalists && journalistStats.journalists.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center">
                            <ShieldCheck className="mr-2 h-5 w-5" />
                            Journalist Analytics
                        </CardTitle>
                        <CardDescription>
                            Subscriber statistics for all journalists ({journalistStats.total_subscriptions} total subscriptions)
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="rounded-md border overflow-x-auto">
                            <table className="w-full min-w-[640px] text-sm">
                                <thead>
                                    <tr className="border-b bg-muted/50">
                                        <th className="p-3 text-left font-medium">Journalist</th>
                                        <th className="p-3 text-left font-medium">Email</th>
                                        <th className="p-3 text-center font-medium">Teams</th>
                                        <th className="p-3 text-right font-medium">Subscribers</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {journalistStats.journalists.map((journalist, idx) => (
                                        <tr key={journalist.journalist_id} className={idx % 2 === 0 ? 'bg-background' : 'bg-muted/20'}>
                                            <td className="p-3">
                                                <div className="flex items-center gap-2">
                                                    {journalist.profile_image_url ? (
                                                        <img
                                                            src={journalist.profile_image_url}
                                                            alt={journalist.journalist_name}
                                                            className="h-8 w-8 rounded-full object-cover"
                                                        />
                                                    ) : (
                                                        <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-semibold text-primary">
                                                            {journalist.journalist_name?.substring(0, 2).toUpperCase()}
                                                        </div>
                                                    )}
                                                    <span className="font-medium">{journalist.journalist_name}</span>
                                                </div>
                                            </td>
                                            <td className="p-3 text-sm text-muted-foreground">{journalist.journalist_email}</td>
                                            <td className="p-3 text-center">
                                                <Badge variant="outline" className="text-xs">
                                                    {journalist.teams_count} {journalist.teams_count === 1 ? 'team' : 'teams'}
                                                </Badge>
                                            </td>
                                            <td className="p-3 text-right">
                                                <div className="flex items-center justify-end gap-2">
                                                    <Users className="h-4 w-4 text-muted-foreground" />
                                                    <span className="text-lg font-semibold text-blue-600">
                                                        {journalist.total_subscribers}
                                                    </span>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {journalistStats.journalists.length === 0 && (
                            <p className="text-center py-8 text-muted-foreground">No journalists found</p>
                        )}
                    </CardContent>
                </Card>
            )}

            <div className="flex items-center space-x-2">
                <Search className="h-4 w-4 text-muted-foreground" />
                <Input
                    placeholder="Search users..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="max-w-sm"
                />
            </div>

            <div className="grid gap-4">
                {filteredUsers.length === 0 ? (
                    <Card>
                        <CardContent className="pt-6 text-center text-muted-foreground">
                            No users found matching your search.
                        </CardContent>
                    </Card>
                ) : (
                    filteredUsers.map((user) => (
                        <Card key={user.id}>
                            <CardHeader className="pb-2">
                                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <CardTitle className="text-lg">{user.display_name || 'No Name'}</CardTitle>
                                        {user.is_journalist && (
                                            <Badge variant="default" className="bg-blue-600 hover:bg-blue-700">
                                                <ShieldCheck className="h-3 w-3 mr-1" /> Journalist
                                            </Badge>
                                        )}
                                        {user.is_editor && (
                                            <Badge variant="default" className="bg-purple-600 hover:bg-purple-700">
                                                <Edit className="h-3 w-3 mr-1" /> Editor
                                            </Badge>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-2 flex-wrap sm:justify-end">
                                        <span className="text-sm text-muted-foreground break-all sm:mr-2">{user.email}</span>
                                        {user.is_journalist && (
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => handleEditCoverage(user)}
                                                className="text-blue-600 border-blue-200 hover:bg-blue-50"
                                            >
                                                <Edit className="h-3 w-3 mr-1" />
                                                Edit Coverage
                                            </Button>
                                        )}
                                        <DropdownMenu>
                                            <DropdownMenuTrigger asChild>
                                                <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                                                    <span className="sr-only">Open menu</span>
                                                    <MoreVertical className="h-4 w-4" />
                                                </Button>
                                            </DropdownMenuTrigger>
                                            <DropdownMenuContent align="start">
                                                <DropdownMenuLabel>Actions</DropdownMenuLabel>
                                                <DropdownMenuItem onClick={() => handleToggleJournalist(user)}>
                                                    {user.is_journalist ? 'Revoke Journalist' : 'Make Journalist'}
                                                </DropdownMenuItem>
                                                <DropdownMenuItem onClick={() => handleToggleEditor(user)}>
                                                    {user.is_editor ? 'Revoke Editor' : 'Make Editor'}
                                                </DropdownMenuItem>
                                            </DropdownMenuContent>
                                        </DropdownMenu>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="grid md:grid-cols-2 gap-4">
                                    <div>
                                        <h4 className="text-sm font-medium mb-2 text-muted-foreground">Following ({user.following?.length || 0})</h4>
                                        <div className="flex flex-wrap gap-2">
                                            {user.following && user.following.length > 0 ? (
                                                user.following.map((team) => (
                                                    <Badge key={team.team_id} variant="outline">
                                                        {team.name}
                                                    </Badge>
                                                ))
                                            ) : (
                                                <span className="text-sm text-muted-foreground italic">Not following any teams</span>
                                            )}
                                        </div>
                                    </div>
                                    {user.is_journalist && (
                                        <div>
                                            <h4 className="text-sm font-medium mb-2 text-muted-foreground">Reporting On ({user.reporting?.length || 0})</h4>
                                            <div className="flex flex-wrap gap-2">
                                                {user.reporting && user.reporting.length > 0 ? (
                                                    user.reporting.map((team) => (
                                                        <Badge key={team.team_id} variant="secondary">
                                                            {team.name}
                                                        </Badge>
                                                    ))
                                                ) : (
                                                    <span className="text-sm text-muted-foreground italic">No teams assigned</span>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    ))
                )}
            </div>

            {/* Invite Dialog */}
            <Dialog open={inviteDialogOpen} onOpenChange={setInviteDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Invite User</DialogTitle>
                        <DialogDescription>
                            Enter the email address to invite a new user. They will be created as a journalist by default if you use this form.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="email">Email Address</Label>
                            <Input
                                id="email"
                                type="email"
                                placeholder="user@example.com"
                                value={inviteEmail}
                                onChange={(e) => setInviteEmail(e.target.value)}
                                onKeyPress={(e) => e.key === 'Enter' && handleInviteJournalist()}
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setInviteDialogOpen(false)} disabled={inviting}>
                            Cancel
                        </Button>
                        <Button onClick={handleInviteJournalist} disabled={inviting || !inviteEmail.trim()}>
                            {inviting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Invite
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Edit Coverage Dialog */}
            <Dialog open={!!editingCoverageUser} onOpenChange={handleCloseCoverageDialog}>
                <DialogContent className="max-w-2xl">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Edit className="h-5 w-5" />
                            Edit Coverage: {editingCoverageUser?.display_name}
                        </DialogTitle>
                        <DialogDescription>
                            Configure which teams and players this writer can cover.
                        </DialogDescription>
                    </DialogHeader>

                    {loadingAssignments ? (
                        <div className="flex items-center justify-center py-12">
                            <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
                            <span className="ml-2 text-muted-foreground">Loading assignments...</span>
                        </div>
                    ) : (
                        <Tabs value={coverageTab} onValueChange={setCoverageTab} className="w-full">
                            <TabsList className="grid w-full grid-cols-2">
                                <TabsTrigger value="parent" className="flex items-center gap-2">
                                    <Building2 className="h-4 w-4" />
                                    Parent Clubs
                                    {selectedParentClubs.length > 0 && (
                                        <Badge variant="secondary" className="ml-1 text-xs">
                                            {selectedParentClubs.length}
                                        </Badge>
                                    )}
                                </TabsTrigger>
                                <TabsTrigger value="loan" className="flex items-center gap-2">
                                    <MapPin className="h-4 w-4" />
                                    Loan Teams
                                    {selectedLoanTeams.length > 0 && (
                                        <Badge variant="secondary" className="ml-1 text-xs">
                                            {selectedLoanTeams.length}
                                        </Badge>
                                    )}
                                </TabsTrigger>
                            </TabsList>

                            <TabsContent value="parent" className="space-y-4 mt-4">
                                <div className="rounded-lg bg-blue-50 border border-blue-200 p-4">
                                    <h4 className="font-medium text-blue-800 flex items-center gap-2 mb-1">
                                        <Building2 className="h-4 w-4" />
                                        Outgoing Loans Coverage
                                    </h4>
                                    <p className="text-sm text-blue-700">
                                        This writer can report on <strong>all players loaned out from</strong> these parent clubs,
                                        regardless of their current loan destination.
                                    </p>
                                </div>

                                <div className="space-y-2">
                                    <Label>Select Parent Clubs</Label>
                                    <TeamMultiSelect
                                        teams={allTeams.map(t => ({ ...t, id: t.team_id }))}
                                        value={selectedParentClubs}
                                        onChange={setSelectedParentClubs}
                                    />
                                </div>
                            </TabsContent>

                            <TabsContent value="loan" className="space-y-4 mt-4">
                                <div className="rounded-lg bg-green-50 border border-green-200 p-4">
                                    <h4 className="font-medium text-green-800 flex items-center gap-2 mb-1">
                                        <MapPin className="h-4 w-4" />
                                        Incoming Loans Coverage
                                    </h4>
                                    <p className="text-sm text-green-700">
                                        This writer can report on <strong>all players currently on loan at</strong> these clubs,
                                        regardless of which parent club they belong to.
                                    </p>
                                </div>

                                {/* Current Loan Team Assignments */}
                                <div className="space-y-2">
                                    <Label>Assigned Loan Teams</Label>
                                    {selectedLoanTeams.length === 0 ? (
                                        <p className="text-sm text-muted-foreground italic py-2">No loan teams assigned yet</p>
                                    ) : (
                                        <div className="flex flex-wrap gap-2">
                                            {selectedLoanTeams.map((lt) => (
                                                <Badge
                                                    key={lt.loan_team_name}
                                                    variant="secondary"
                                                    className={`py-1.5 pl-3 pr-2 ${lt.loan_team_id
                                                            ? 'bg-green-100 text-green-800 border-green-300'
                                                            : 'bg-amber-100 text-amber-800 border-amber-300'
                                                        }`}
                                                >
                                                    {lt.loan_team_name}
                                                    {!lt.loan_team_id && (
                                                        <span className="ml-1 text-xs opacity-70">(custom)</span>
                                                    )}
                                                    <button
                                                        onClick={() => handleRemoveLoanTeam(lt.loan_team_name)}
                                                        className="ml-2 rounded-full p-0.5 hover:bg-red-200 text-red-600"
                                                        type="button"
                                                    >
                                                        <X className="h-3 w-3" />
                                                    </button>
                                                </Badge>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* Add Loan Team */}
                                <div className="space-y-2">
                                    <Label htmlFor="newLoanTeam">Add Loan Team</Label>
                                    <div className="flex gap-2">
                                        <Input
                                            id="newLoanTeam"
                                            placeholder="Enter team name (e.g., Falkirk)"
                                            value={newLoanTeamName}
                                            onChange={(e) => setNewLoanTeamName(e.target.value)}
                                            onKeyPress={(e) => e.key === 'Enter' && handleAddLoanTeam()}
                                            list="teamSuggestions"
                                        />
                                        <Button
                                            type="button"
                                            variant="outline"
                                            onClick={handleAddLoanTeam}
                                            disabled={!newLoanTeamName.trim()}
                                        >
                                            <Plus className="h-4 w-4" />
                                        </Button>
                                    </div>
                                    <datalist id="teamSuggestions">
                                        {loanTeamOptions.map(t => (
                                            <option key={`${t.loan_team_id || 'custom'}-${t.name}`} value={t.name} />
                                        ))}
                                    </datalist>
                                    <p className="text-xs text-muted-foreground">
                                        Type a team name and press Enter. Custom team names (not in database) will be marked as "(custom)".
                                    </p>
                                </div>
                            </TabsContent>
                        </Tabs>
                    )}

                    <DialogFooter className="mt-4">
                        <Button variant="outline" onClick={handleCloseCoverageDialog} disabled={assigning}>
                            Cancel
                        </Button>
                        <Button
                            onClick={handleSaveCoverage}
                            disabled={assigning || loadingAssignments}
                            className="bg-blue-600 hover:bg-blue-700"
                        >
                            {assigning && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Save Coverage
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Confirm Role Change Dialog */}
            <Dialog open={!!confirmRoleChangeUser} onOpenChange={() => setConfirmRoleChangeUser(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            {confirmRoleChangeUser?.is_journalist ? 'Revoke Journalist Status' : 'Grant Journalist Status'}
                        </DialogTitle>
                        <DialogDescription>
                            Are you sure you want to {confirmRoleChangeUser?.is_journalist ? 'revoke journalist status from' : 'make'} {confirmRoleChangeUser?.display_name} {confirmRoleChangeUser?.is_journalist ? '' : 'a journalist'}?
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setConfirmRoleChangeUser(null)} disabled={togglingRole}>
                            Cancel
                        </Button>
                        <Button onClick={confirmToggleJournalist} disabled={togglingRole}>
                            {togglingRole && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Confirm
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Confirm Editor Role Change Dialog */}
            <Dialog open={!!confirmEditorChangeUser} onOpenChange={() => setConfirmEditorChangeUser(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            {confirmEditorChangeUser?.is_editor ? 'Revoke Editor Status' : 'Grant Editor Status'}
                        </DialogTitle>
                        <DialogDescription>
                            {confirmEditorChangeUser?.is_editor
                                ? `Are you sure you want to revoke editor status from ${confirmEditorChangeUser?.display_name}? They will no longer be able to manage external writers.`
                                : `Are you sure you want to make ${confirmEditorChangeUser?.display_name} an editor? They will be able to create and manage external writers.`
                            }
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setConfirmEditorChangeUser(null)} disabled={togglingEditor}>
                            Cancel
                        </Button>
                        <Button onClick={confirmToggleEditor} disabled={togglingEditor}>
                            {togglingEditor && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Confirm
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
