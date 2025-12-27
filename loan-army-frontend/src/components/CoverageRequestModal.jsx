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
import { Loader2, Search, Building2, Users } from 'lucide-react'
import { APIService } from '@/lib/api'

export function CoverageRequestModal({ open, onOpenChange, onSuccess }) {
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

    // Reset form when modal opens
    useEffect(() => {
        if (open) {
            setCoverageType('loan_team')
            setTeamSearch('')
            setSearchResults([])
            setSelectedTeam(null)
            setCustomTeamName('')
            setUseCustomTeam(false)
            setRequestMessage('')
            setError('')
        }
    }, [open])

    // Search teams when typing
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

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Users className="h-5 w-5" />
                        Request Coverage Access
                    </DialogTitle>
                    <DialogDescription>
                        Request permission to write about players for a specific team. 
                        An admin will review your request.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-6 py-4">
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
                                    flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all
                                    ${coverageType === 'loan_team' 
                                        ? 'border-blue-500 bg-blue-50' 
                                        : 'border-gray-200 hover:border-gray-300'
                                    }
                                `}
                            >
                                <RadioGroupItem value="loan_team" className="mt-1" />
                                <div>
                                    <div className="font-medium">Loan Destination</div>
                                    <div className="text-xs text-gray-500 mt-1">
                                        Cover ALL players loaned to a specific club (e.g., Falkirk)
                                    </div>
                                </div>
                            </label>
                            
                            <label
                                className={`
                                    flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all
                                    ${coverageType === 'parent_club' 
                                        ? 'border-blue-500 bg-blue-50' 
                                        : 'border-gray-200 hover:border-gray-300'
                                    }
                                `}
                            >
                                <RadioGroupItem value="parent_club" className="mt-1" />
                                <div>
                                    <div className="font-medium">Parent Club</div>
                                    <div className="text-xs text-gray-500 mt-1">
                                        Cover all loanees FROM a parent club (e.g., Man United)
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

                    {error && (
                        <div className="p-3 bg-red-50 text-red-700 rounded-lg text-sm">
                            {error}
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                        Cancel
                    </Button>
                    <Button onClick={handleSubmit} disabled={loading}>
                        {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Submit Request
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}



