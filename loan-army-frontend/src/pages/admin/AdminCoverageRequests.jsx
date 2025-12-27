import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { 
    Loader2, 
    CheckCircle, 
    XCircle, 
    Clock, 
    Building2, 
    MapPin, 
    Users,
    MessageSquare
} from 'lucide-react'
import { APIService } from '@/lib/api'

export function AdminCoverageRequests() {
    const [requests, setRequests] = useState([])
    const [summary, setSummary] = useState({ pending: 0, approved: 0, denied: 0, total: 0 })
    const [loading, setLoading] = useState(true)
    const [activeTab, setActiveTab] = useState('pending')
    
    // Denial dialog state
    const [denyingRequest, setDenyingRequest] = useState(null)
    const [denialReason, setDenialReason] = useState('')
    const [processing, setProcessing] = useState(false)

    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        try {
            setLoading(true)
            const data = await APIService.adminListCoverageRequests()
            setRequests(data.requests || [])
            setSummary(data.summary || { pending: 0, approved: 0, denied: 0, total: 0 })
        } catch (error) {
            console.error('Failed to load coverage requests:', error)
        } finally {
            setLoading(false)
        }
    }

    const handleApprove = async (requestId) => {
        try {
            setProcessing(true)
            await APIService.adminApproveCoverageRequest(requestId)
            loadData()
        } catch (error) {
            console.error('Failed to approve request:', error)
            alert(error.message || 'Failed to approve request')
        } finally {
            setProcessing(false)
        }
    }

    const handleDeny = async () => {
        if (!denyingRequest) return
        
        try {
            setProcessing(true)
            await APIService.adminDenyCoverageRequest(denyingRequest.id, denialReason.trim() || null)
            setDenyingRequest(null)
            setDenialReason('')
            loadData()
        } catch (error) {
            console.error('Failed to deny request:', error)
            alert(error.message || 'Failed to deny request')
        } finally {
            setProcessing(false)
        }
    }

    const filteredRequests = requests.filter(r => {
        if (activeTab === 'all') return true
        return r.status === activeTab
    })

    const getStatusBadge = (status) => {
        switch (status) {
            case 'pending':
                return <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200">
                    <Clock className="h-3 w-3 mr-1" /> Pending
                </Badge>
            case 'approved':
                return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                    <CheckCircle className="h-3 w-3 mr-1" /> Approved
                </Badge>
            case 'denied':
                return <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200">
                    <XCircle className="h-3 w-3 mr-1" /> Denied
                </Badge>
            default:
                return null
        }
    }

    const getCoverageTypeBadge = (type) => {
        if (type === 'parent_club') {
            return <Badge variant="secondary" className="bg-blue-50 text-blue-700">
                <Building2 className="h-3 w-3 mr-1" /> Parent Club
            </Badge>
        } else {
            return <Badge variant="secondary" className="bg-green-50 text-green-700">
                <MapPin className="h-3 w-3 mr-1" /> Loan Team
            </Badge>
        }
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                    <Users className="h-6 w-6" />
                    Coverage Requests
                </h1>
                <p className="text-gray-500 mt-1">
                    Review and manage writer coverage requests
                </p>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-4 gap-4">
                <Card className="bg-amber-50 border-amber-200">
                    <CardHeader className="pb-2">
                        <CardDescription className="text-amber-700">Pending</CardDescription>
                        <CardTitle className="text-3xl text-amber-900">{summary.pending}</CardTitle>
                    </CardHeader>
                </Card>
                <Card className="bg-green-50 border-green-200">
                    <CardHeader className="pb-2">
                        <CardDescription className="text-green-700">Approved</CardDescription>
                        <CardTitle className="text-3xl text-green-900">{summary.approved}</CardTitle>
                    </CardHeader>
                </Card>
                <Card className="bg-red-50 border-red-200">
                    <CardHeader className="pb-2">
                        <CardDescription className="text-red-700">Denied</CardDescription>
                        <CardTitle className="text-3xl text-red-900">{summary.denied}</CardTitle>
                    </CardHeader>
                </Card>
                <Card className="bg-gray-50 border-gray-200">
                    <CardHeader className="pb-2">
                        <CardDescription className="text-gray-700">Total</CardDescription>
                        <CardTitle className="text-3xl text-gray-900">{summary.total}</CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Requests Table */}
            <Card>
                <CardHeader>
                    <Tabs value={activeTab} onValueChange={setActiveTab}>
                        <TabsList>
                            <TabsTrigger value="pending">
                                Pending ({summary.pending})
                            </TabsTrigger>
                            <TabsTrigger value="approved">Approved</TabsTrigger>
                            <TabsTrigger value="denied">Denied</TabsTrigger>
                            <TabsTrigger value="all">All</TabsTrigger>
                        </TabsList>
                    </Tabs>
                </CardHeader>
                <CardContent>
                    {filteredRequests.length === 0 ? (
                        <div className="text-center py-8 text-gray-500">
                            No {activeTab === 'all' ? '' : activeTab} requests found.
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Writer</TableHead>
                                    <TableHead>Coverage Type</TableHead>
                                    <TableHead>Team</TableHead>
                                    <TableHead>Message</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead>Requested</TableHead>
                                    <TableHead className="text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {filteredRequests.map(req => (
                                    <TableRow key={req.id}>
                                        <TableCell>
                                            <div>
                                                <div className="font-medium">{req.writer_name}</div>
                                                <div className="text-xs text-gray-500">{req.writer_email}</div>
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            {getCoverageTypeBadge(req.coverage_type)}
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex items-center gap-2">
                                                {req.team_logo && (
                                                    <img 
                                                        src={req.team_logo} 
                                                        alt="" 
                                                        className="h-5 w-5 object-contain"
                                                    />
                                                )}
                                                <span className="font-medium">{req.team_name}</span>
                                                {req.is_custom_team && (
                                                    <Badge variant="outline" className="text-xs">Custom</Badge>
                                                )}
                                            </div>
                                        </TableCell>
                                        <TableCell className="max-w-[200px]">
                                            {req.request_message ? (
                                                <div className="flex items-start gap-1 text-sm text-gray-600">
                                                    <MessageSquare className="h-4 w-4 mt-0.5 flex-shrink-0" />
                                                    <span className="truncate">{req.request_message}</span>
                                                </div>
                                            ) : (
                                                <span className="text-gray-400 text-sm">No message</span>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            {getStatusBadge(req.status)}
                                            {req.denial_reason && (
                                                <div className="text-xs text-red-600 mt-1 truncate max-w-[150px]">
                                                    {req.denial_reason}
                                                </div>
                                            )}
                                        </TableCell>
                                        <TableCell className="text-sm text-gray-500">
                                            {new Date(req.requested_at).toLocaleDateString()}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            {req.status === 'pending' && (
                                                <div className="flex gap-2 justify-end">
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        className="text-green-600 border-green-200 hover:bg-green-50"
                                                        onClick={() => handleApprove(req.id)}
                                                        disabled={processing}
                                                    >
                                                        <CheckCircle className="h-4 w-4 mr-1" />
                                                        Approve
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        className="text-red-600 border-red-200 hover:bg-red-50"
                                                        onClick={() => setDenyingRequest(req)}
                                                        disabled={processing}
                                                    >
                                                        <XCircle className="h-4 w-4 mr-1" />
                                                        Deny
                                                    </Button>
                                                </div>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>

            {/* Denial Dialog */}
            <Dialog open={!!denyingRequest} onOpenChange={(open) => !open && setDenyingRequest(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Deny Coverage Request</DialogTitle>
                        <DialogDescription>
                            Deny {denyingRequest?.writer_name}'s request to cover {denyingRequest?.team_name}?
                        </DialogDescription>
                    </DialogHeader>
                    <div className="py-4">
                        <Textarea
                            placeholder="Reason for denial (optional)"
                            value={denialReason}
                            onChange={(e) => setDenialReason(e.target.value)}
                            rows={3}
                        />
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDenyingRequest(null)}>
                            Cancel
                        </Button>
                        <Button 
                            variant="destructive" 
                            onClick={handleDeny}
                            disabled={processing}
                        >
                            {processing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Deny Request
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}



