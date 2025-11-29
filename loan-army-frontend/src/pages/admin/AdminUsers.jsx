import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Loader2, Users, Search, ShieldCheck, Shield, UserPlus, Edit, MoreVertical } from 'lucide-react'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { APIService } from '@/lib/api'
import TeamMultiSelect from '@/components/ui/TeamMultiSelect'

export function AdminUsers() {
    const [users, setUsers] = useState([])
    const [allTeams, setAllTeams] = useState([])
    const [journalistStats, setJournalistStats] = useState(null)
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')

    // Dialog states
    const [inviteDialogOpen, setInviteDialogOpen] = useState(false)
    const [inviteEmail, setInviteEmail] = useState('')
    const [inviting, setInviting] = useState(false)

    const [editingTeamsUser, setEditingTeamsUser] = useState(null)
    const [selectedTeams, setSelectedTeams] = useState([])
    const [assigning, setAssigning] = useState(false)

    const [confirmRoleChangeUser, setConfirmRoleChangeUser] = useState(null)
    const [togglingRole, setTogglingRole] = useState(false)

    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        try {
            setLoading(true)
            const [usersData, teamsData, statsData] = await Promise.all([
                APIService.adminGetUsers(),
                APIService.getTeams(),
                APIService.adminGetJournalistStats().catch(() => null)
            ])
            setUsers(usersData || [])
            setAllTeams(teamsData || [])
            setJournalistStats(statsData)
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

    const handleEditTeams = (user) => {
        setEditingTeamsUser(user)
        // Pre-select current teams (reporting on)
        const currentTeamIds = user.reporting?.map(t => t.team_id) || []
        setSelectedTeams(currentTeamIds)
    }

    const handleSaveTeams = async () => {
        if (!editingTeamsUser) return

        try {
            setAssigning(true)
            await APIService.adminUpdateJournalistTeams(editingTeamsUser.id, selectedTeams)
            setEditingTeamsUser(null)
            setSelectedTeams([])
            loadData() // Reload list
        } catch (error) {
            console.error('Failed to update teams:', error)
            alert(error.message || 'Failed to update team assignments')
        } finally {
            setAssigning(false)
        }
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
                                    </div>
                                    <div className="flex items-center gap-2 flex-wrap sm:justify-end">
                                        <span className="text-sm text-muted-foreground break-all sm:mr-2">{user.email}</span>
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
                                                {user.is_journalist && (
                                                    <DropdownMenuItem onClick={() => handleEditTeams(user)}>
                                                        Assign Teams
                                                    </DropdownMenuItem>
                                                )}
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

            {/* Edit Teams Dialog */}
            <Dialog open={!!editingTeamsUser} onOpenChange={() => setEditingTeamsUser(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Assign Teams</DialogTitle>
                        <DialogDescription>
                            Select which teams {editingTeamsUser?.display_name} can write for.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label>Teams</Label>
                            <TeamMultiSelect
                                teams={allTeams.map(t => ({ ...t, id: t.team_id }))}
                                value={selectedTeams}
                                onChange={setSelectedTeams}
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setEditingTeamsUser(null)} disabled={assigning}>
                            Cancel
                        </Button>
                        <Button onClick={handleSaveTeams} disabled={assigning}>
                            {assigning && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Save
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
        </div>
    )
}
