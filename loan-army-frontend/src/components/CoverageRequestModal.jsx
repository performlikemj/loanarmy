import React, { useState, useEffect } from 'react'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, Search, Building2, Users, MapPin, ArrowRight } from 'lucide-react'
import { APIService } from '@/lib/api'

export function CoverageRequestModal({ open, onOpenChange, onSuccess }) {
    const [activeTab, setActiveTab] = useState('browse')
    const [coverageType, setCoverageType] = useState('loan_team')
    const [teamSearch, setTeamSearch] = useState('')
    const [searchResults, setSearchResults] = useState([])
    const [selectedTeam, setSelectedTeam] = useState(null)
    const [customTeamName, setCustomTeamName] = useState('')
    const [useCustomTeam, setUseCustomTeam] = useState(false)
    const [requestMessage, setRequestMessage] = useState('')
    const [loading, setLoading] = useState(false)
    const [searching, setSearching] = useState(false)
    const [error, setError] = useState('')

    // Browse state
    const [destinations, setDestinations] = useState([])
    const [loadingDestinations, setLoadingDestinations] = useState(false)
    const [destinationFilter, setDestinationFilter] = useState('')

    // Reset form when modal opens
    useEffect(() => {
        if (open) {
            setActiveTab('browse')
            setCoverageType('loan_team')
            setTeamSearch('')
            setSearchResults([])
            setSelectedTeam(null)
            setCustomTeamName('')
            setUseCustomTeam(false)
            setRequestMessage('')
            setError('')
            setDestinationFilter('')
            loadDestinations()
        }
    }, [open])

    const loadDestinations = async () => {
        setLoadingDestinations(true)
        try {
            const res = await APIService.getLoanDestinations()
            setDestinations(res.destinations || [])
        } catch (err) {
            console.error('Failed to load destinations', err)
        } finally {
            setLoadingDestinations(false)
        }
    }

    // Search teams when typing (Manual Entry)
    useEffect(() => {
        const searchTeams = async () => {
            if (!teamSearch || teamSearch.length < 2) {
                setSearchResults([])
                return
            }

            setSearching(true)
            try {
                const teams = await APIService.getTeams()
                const filtered = teams.filter(t =>
                    t.name.toLowerCase().includes(teamSearch.toLowerCase())
                ).slice(0, 10)
                setSearchResults(filtered)
            } catch (err) {
                console.error('Failed to search teams', err)
            } finally {
                setSearching(false)
            }
        }

        const debounce = setTimeout(searchTeams, 300)
        return () => clearTimeout(debounce)
    }, [teamSearch])

    const handleSelectTeam = (team) => {
        setSelectedTeam(team)
        setTeamSearch(team.name)
        setSearchResults([])
        setUseCustomTeam(false)
        setCustomTeamName('')
    }

    const handleSelectDestination = (dest) => {
        // Pre-fill manual form with selected destination
        setCoverageType('loan_team')
        setUseCustomTeam(true) // Treat as custom since we might not have a full team object with ID
        setCustomTeamName(dest.name)
        if (dest.team_id) {
            // If we have an ID, try to set it as a selected team if possible, 
            // but for now custom name is safer to ensure it matches the loan destination name exactly
            // We can store the ID if we want to be more precise later
            setUseCustomTeam(false)
            setSelectedTeam({ id: dest.team_id, name: dest.name })
            setTeamSearch(dest.name)
        } else {
            setTeamSearch(dest.name)
        }

        setActiveTab('manual')
    }

    const handleSubmit = async () => {
        setError('')

        // Validate
        const teamName = useCustomTeam ? customTeamName.trim() : selectedTeam?.name
        if (!teamName) {
            setError('Please select or enter a team name')
            return
        }

        setLoading(true)
        try {
            await APIService.submitCoverageRequest({
                coverage_type: coverageType,
                team_id: useCustomTeam ? null : selectedTeam?.id,
                team_name: teamName,
                request_message: requestMessage.trim() || null
            })

            onSuccess?.()
            onOpenChange(false)
        } catch (err) {
            console.error('Failed to submit coverage request', err)
            setError(err.message || 'Failed to submit request')
        } finally {
            setLoading(false)
        }
    }

    const filteredDestinations = destinations.filter(d =>
        d.name.toLowerCase().includes(destinationFilter.toLowerCase())
    )

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[600px] max-h-[85vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Users className="h-5 w-5" />
                        Request Coverage Access
                    </DialogTitle>
                    <DialogDescription>
                        Find a team to cover or request a new one.
                    </DialogDescription>
                </DialogHeader>

                <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
                    <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="browse">Browse Destinations</TabsTrigger>
                        <TabsTrigger value="manual">Manual Request</TabsTrigger>
                    </TabsList>

                    <TabsContent value="browse" className="flex-1 flex flex-col min-h-0 mt-4 space-y-4">
                        <div className="relative">
                            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-500" />
                            <Input
                                placeholder="Filter destinations..."
                                value={destinationFilter}
                                onChange={(e) => setDestinationFilter(e.target.value)}
                                className="pl-9"
                            />
                        </div>

                        <div className="flex-1 overflow-y-auto border rounded-md bg-gray-50/50 p-2 space-y-2 min-h-[300px]">
                            {loadingDestinations ? (
                                <div className="flex items-center justify-center h-full">
                                    <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
                                </div>
                            ) : filteredDestinations.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-full text-gray-500 space-y-2">
                                    <MapPin className="h-8 w-8 text-gray-300" />
                                    <p>No destinations found matching "{destinationFilter}"</p>
                                    <Button variant="link" onClick={() => setActiveTab('manual')}>
                                        Make a manual request
                                    </Button>
                                </div>
                            ) : (
                                filteredDestinations.map((dest, idx) => (
                                    <div
                                        key={idx}
                                        className="flex items-center justify-between p-3 bg-white border rounded-lg hover:border-blue-300 hover:shadow-sm transition-all cursor-pointer group"
                                        onClick={() => handleSelectDestination(dest)}
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className="h-8 w-8 rounded-full bg-gray-100 flex items-center justify-center text-gray-500 font-bold text-xs">
                                                {dest.name.substring(0, 2).toUpperCase()}
                                            </div>
                                            <div>
                                                <div className="font-medium text-sm text-gray-900">{dest.name}</div>
                                                <div className="text-xs text-gray-500">
                                                    {dest.player_count} active player{dest.player_count !== 1 ? 's' : ''}
                                                </div>
                                            </div>
                                        </div>
                                        <Button size="sm" variant="ghost" className="opacity-0 group-hover:opacity-100">
                                            Request <ArrowRight className="ml-1 h-3 w-3" />
                                        </Button>
                                    </div>
                                ))
                            )}
                        </div>
                    </TabsContent>

                    <TabsContent value="manual" className="mt-4 space-y-4 overflow-y-auto pr-1">
                        {/* Coverage Type Selection */}
                        <div className="space-y-3">
                            <Label>Coverage Type</Label>
                            <RadioGroup
                                value={coverageType}
                                onValueChange={setCoverageType}
                                className="grid grid-cols-2 gap-3"
                            >
                                <label
                                    className={`
                                        flex items-start gap-3 p-3 rounded-lg border-2 cursor-pointer transition-all
                                        ${coverageType === 'loan_team'
                                            ? 'border-blue-500 bg-blue-50'
                                            : 'border-gray-200 hover:border-gray-300'
                                        }
                                    `}
                                >
                                    <RadioGroupItem value="loan_team" className="mt-1" />
                                    <div>
                                        <div className="font-medium text-sm">Loan Destination</div>
                                        <div className="text-[10px] text-gray-500 mt-0.5">
                                            Cover players at a specific club
                                        </div>
                                    </div>
                                </label>

                                <label
                                    className={`
                                        flex items-start gap-3 p-3 rounded-lg border-2 cursor-pointer transition-all
                                        ${coverageType === 'parent_club'
                                            ? 'border-blue-500 bg-blue-50'
                                            : 'border-gray-200 hover:border-gray-300'
                                        }
                                    `}
                                >
                                    <RadioGroupItem value="parent_club" className="mt-1" />
                                    <div>
                                        <div className="font-medium text-sm">Parent Club</div>
                                        <div className="text-[10px] text-gray-500 mt-0.5">
                                            Cover loanees FROM a club
                                        </div>
                                    </div>
                                </label>
                            </RadioGroup>
                        </div>

                        {/* Team Selection */}
                        <div className="space-y-3">
                            <Label>
                                {coverageType === 'loan_team' ? 'Loan Destination Team' : 'Parent Club'}
                            </Label>

                            {/* Search or Custom Toggle */}
                            <div className="flex gap-2 mb-2">
                                <Button
                                    type="button"
                                    size="sm"
                                    variant={!useCustomTeam ? "default" : "outline"}
                                    onClick={() => setUseCustomTeam(false)}
                                >
                                    <Search className="h-4 w-4 mr-1" /> Search
                                </Button>
                                <Button
                                    type="button"
                                    size="sm"
                                    variant={useCustomTeam ? "default" : "outline"}
                                    onClick={() => {
                                        setUseCustomTeam(true)
                                        setSelectedTeam(null)
                                        setTeamSearch('')
                                    }}
                                >
                                    <Building2 className="h-4 w-4 mr-1" /> Custom
                                </Button>
                            </div>

                            {!useCustomTeam ? (
                                <div className="relative">
                                    <Input
                                        placeholder="Search for a team..."
                                        value={teamSearch}
                                        onChange={(e) => {
                                            setTeamSearch(e.target.value)
                                            setSelectedTeam(null)
                                        }}
                                        className="pr-8"
                                    />
                                    {searching && (
                                        <Loader2 className="absolute right-3 top-3 h-4 w-4 animate-spin text-gray-400" />
                                    )}

                                    {/* Search Results Dropdown */}
                                    {searchResults.length > 0 && !selectedTeam && (
                                        <div className="absolute z-10 w-full mt-1 bg-white border rounded-lg shadow-lg max-h-48 overflow-y-auto">
                                            {searchResults.map(team => (
                                                <button
                                                    key={team.id}
                                                    type="button"
                                                    className="w-full flex items-center gap-2 px-3 py-2 hover:bg-gray-50 text-left"
                                                    onClick={() => handleSelectTeam(team)}
                                                >
                                                    {team.logo && (
                                                        <img
                                                            src={team.logo}
                                                            alt=""
                                                            className="h-5 w-5 object-contain"
                                                        />
                                                    )}
                                                    <span className="text-sm">{team.name}</span>
                                                    <span className="text-xs text-gray-400 ml-auto">
                                                        {team.country}
                                                    </span>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <Input
                                    placeholder={
                                        coverageType === 'loan_team'
                                            ? "e.g., Falkirk, Plymouth Argyle, Hull City"
                                            : "e.g., Manchester United, Chelsea"
                                    }
                                    value={customTeamName}
                                    onChange={(e) => setCustomTeamName(e.target.value)}
                                />
                            )}

                            {/* Selected Team Display */}
                            {selectedTeam && !useCustomTeam && (
                                <div className="flex items-center gap-2 p-2 bg-blue-50 rounded-lg">
                                    {selectedTeam.logo && (
                                        <img
                                            src={selectedTeam.logo}
                                            alt=""
                                            className="h-6 w-6 object-contain"
                                        />
                                    )}
                                    <span className="font-medium text-sm">{selectedTeam.name}</span>
                                </div>
                            )}
                        </div>

                        {/* Message */}
                        <div className="space-y-2">
                            <Label>Why do you want to cover this team? (optional)</Label>
                            <Textarea
                                placeholder="e.g., I'm a local supporter who attends all home games..."
                                value={requestMessage}
                                onChange={(e) => setRequestMessage(e.target.value)}
                                rows={3}
                            />
                        </div>
                    </TabsContent>
                </Tabs>

                <DialogFooter className="mt-4">
                    {activeTab === 'manual' && (
                        <>
                            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                                Cancel
                            </Button>
                            <Button onClick={handleSubmit} disabled={loading}>
                                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Submit Request
                            </Button>
                        </>
                    )}
                    {activeTab === 'browse' && (
                        <Button variant="outline" onClick={() => onOpenChange(false)}>
                            Close
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}



