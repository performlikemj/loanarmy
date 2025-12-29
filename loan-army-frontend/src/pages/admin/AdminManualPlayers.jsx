import { useState, useEffect, useCallback } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, CheckCircle, XCircle, Clock, User, Shield, MessageSquare } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

export function AdminManualPlayers() {
    const [submissions, setSubmissions] = useState([])
    const [loading, setLoading] = useState(true)
    const [activeTab, setActiveTab] = useState('pending')
    const [reviewDialog, setReviewDialog] = useState({ open: false, submission: null, action: null })
    const [adminNotes, setAdminNotes] = useState('')
    const [processing, setProcessing] = useState(false)

    const loadSubmissions = useCallback(async () => {
        setLoading(true)
        try {
            const data = await APIService.adminListManualPlayers({ status: activeTab === 'all' ? undefined : activeTab })
            setSubmissions(Array.isArray(data) ? data : [])
        } catch (error) {
            console.error('Failed to load submissions', error)
        } finally {
            setLoading(false)
        }
    }, [activeTab])

    useEffect(() => {
        loadSubmissions()
    }, [loadSubmissions])

    const openReviewDialog = (submission, action) => {
        setReviewDialog({ open: true, submission, action })
        setAdminNotes('')
    }

    const handleReview = async () => {
        if (!reviewDialog.submission || !reviewDialog.action) return

        setProcessing(true)
        try {
            await APIService.adminReviewManualPlayer(reviewDialog.submission.id, {
                status: reviewDialog.action,
                admin_notes: adminNotes
            })
            setReviewDialog({ open: false, submission: null, action: null })
            loadSubmissions()
        } catch (error) {
            console.error('Failed to review submission', error)
            alert('Failed to review submission: ' + error.message)
        } finally {
            setProcessing(false)
        }
    }

    const getStatusBadge = (status) => {
        switch (status) {
            case 'approved':
                return <Badge className="bg-green-600"><CheckCircle className="h-3 w-3 mr-1" /> Approved</Badge>
            case 'rejected':
                return <Badge variant="destructive"><XCircle className="h-3 w-3 mr-1" /> Rejected</Badge>
            default:
                return <Badge variant="secondary"><Clock className="h-3 w-3 mr-1" /> Pending</Badge>
        }
    }

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Manual Player Submissions</h2>
                <p className="text-muted-foreground mt-1">
                    Review and manage player suggestions from writers.
                </p>
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
                <TabsList>
                    <TabsTrigger value="pending">Pending</TabsTrigger>
                    <TabsTrigger value="approved">Approved</TabsTrigger>
                    <TabsTrigger value="rejected">Rejected</TabsTrigger>
                    <TabsTrigger value="all">All</TabsTrigger>
                </TabsList>

                <Card>
                    <CardHeader>
                        <CardTitle>Submissions ({submissions.length})</CardTitle>
                        <CardDescription>
                            {activeTab === 'pending' ? 'Submissions waiting for review' : `Submissions with status: ${activeTab}`}
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {loading ? (
                            <div className="flex justify-center py-8">
                                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                            </div>
                        ) : submissions.length === 0 ? (
                            <div className="text-center py-8 text-muted-foreground">
                                No submissions found.
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {submissions.map((sub) => (
                                    <div key={sub.id} className="border rounded-lg p-4 flex flex-col sm:flex-row gap-4 justify-between items-start bg-card">
                                        <div className="space-y-2 flex-1">
                                            <div className="flex items-center gap-2">
                                                <h3 className="font-semibold text-lg">{sub.player_name}</h3>
                                                <Badge variant="outline">{sub.team_name}</Badge>
                                                {getStatusBadge(sub.status)}
                                            </div>

                                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2 text-sm text-muted-foreground">
                                                <div className="flex items-center gap-2">
                                                    <User className="h-4 w-4" />
                                                    Submitted by: <span className="font-medium text-foreground">{sub.user_name}</span>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <Clock className="h-4 w-4" />
                                                    Date: {new Date(sub.created_at).toLocaleDateString()}
                                                </div>
                                                {sub.league_name && (
                                                    <div>League: <span className="text-foreground">{sub.league_name}</span></div>
                                                )}
                                                {sub.position && (
                                                    <div>Position: <span className="text-foreground">{sub.position}</span></div>
                                                )}
                                            </div>

                                            {sub.notes && (
                                                <div className="bg-muted/50 p-3 rounded-md text-sm mt-2">
                                                    <span className="font-medium block mb-1 text-xs uppercase tracking-wider text-muted-foreground">Writer Notes</span>
                                                    {sub.notes}
                                                </div>
                                            )}

                                            {sub.admin_notes && (
                                                <div className="bg-blue-50 text-blue-800 p-3 rounded-md text-sm mt-2 border border-blue-100">
                                                    <span className="font-medium block mb-1 text-xs uppercase tracking-wider flex items-center gap-1">
                                                        <Shield className="h-3 w-3" /> Admin Response
                                                    </span>
                                                    {sub.admin_notes}
                                                </div>
                                            )}
                                        </div>

                                        {sub.status === 'pending' && (
                                            <div className="flex flex-col gap-2 min-w-[120px]">
                                                <Button
                                                    className="w-full bg-green-600 hover:bg-green-700"
                                                    size="sm"
                                                    onClick={() => openReviewDialog(sub, 'approved')}
                                                >
                                                    <CheckCircle className="h-4 w-4 mr-2" /> Approve
                                                </Button>
                                                <Button
                                                    variant="destructive"
                                                    size="sm"
                                                    className="w-full"
                                                    onClick={() => openReviewDialog(sub, 'rejected')}
                                                >
                                                    <XCircle className="h-4 w-4 mr-2" /> Reject
                                                </Button>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </CardContent>
                </Card>
            </Tabs>

            <Dialog open={reviewDialog.open} onOpenChange={(open) => !open && setReviewDialog({ ...reviewDialog, open: false })}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            {reviewDialog.action === 'approved' ? 'Approve Submission' : 'Reject Submission'}
                        </DialogTitle>
                        <DialogDescription>
                            {reviewDialog.action === 'approved'
                                ? 'Confirm that you have added this player to the database or verified they are tracked.'
                                : 'Please provide a reason for rejection.'}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label>Admin Notes (Optional)</Label>
                            <Textarea
                                placeholder={reviewDialog.action === 'approved' ? "e.g. Added to database with ID 123" : "e.g. Player already exists as 'J. Doe'"}
                                value={adminNotes}
                                onChange={(e) => setAdminNotes(e.target.value)}
                            />
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setReviewDialog({ ...reviewDialog, open: false })}>
                            Cancel
                        </Button>
                        <Button
                            variant={reviewDialog.action === 'approved' ? 'default' : 'destructive'}
                            onClick={handleReview}
                            disabled={processing}
                            className={reviewDialog.action === 'approved' ? 'bg-green-600 hover:bg-green-700' : ''}
                        >
                            {processing && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Confirm {reviewDialog.action === 'approved' ? 'Approval' : 'Rejection'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
