import { Loader2, X } from 'lucide-react'
import { Progress } from '@/components/ui/progress'
import { useBackgroundJobs } from '@/context/BackgroundJobsContext'

const JOB_TYPE_LABELS = {
    full_rebuild: 'Full Academy Rebuild',
    seed_big6: 'Big 6 Seeding',
    seed_top5: 'Top 5 League Seeding',
    fix_miscategorized: 'Fix Miscategorized Players',
    reconcile_ids: 'Reconcile Player IDs',
    team_fixtures_sync: 'Team Fixtures Sync',
}

export function SyncOverlay() {
    const { activeJobs, isBlocking, bannerJobs, dismiss } = useBackgroundJobs()

    if (!isBlocking && bannerJobs.length === 0) return null

    const blockingJob = activeJobs.find(
        j => j.status === 'running' && ['full_rebuild', 'seed_big6'].includes(j.type)
    )

    return (
        <>
            {isBlocking && blockingJob && (
                <div className="absolute inset-0 z-30 bg-white/90 backdrop-blur-sm flex items-center justify-center">
                    <div className="max-w-md w-full mx-4 bg-white border rounded-xl shadow-lg p-6 space-y-4">
                        <div className="flex items-center gap-3">
                            <Loader2 className="h-6 w-6 animate-spin text-blue-600 shrink-0" />
                            <div>
                                <h3 className="font-semibold text-lg">System Syncing</h3>
                                <p className="text-sm text-muted-foreground">
                                    {JOB_TYPE_LABELS[blockingJob.type] || blockingJob.type}
                                </p>
                            </div>
                        </div>
                        <p className="text-sm text-gray-700">
                            {blockingJob.current_player || 'Starting...'}
                        </p>
                        <Progress value={((blockingJob.progress || 0) / (blockingJob.total || 1)) * 100} />
                        <p className="text-xs text-muted-foreground">
                            Stage {blockingJob.progress || 0} of {blockingJob.total || '?'}
                        </p>
                        <p className="text-xs text-amber-700 bg-amber-50 rounded p-2">
                            Data is being rebuilt. Other admin pages may show incomplete or empty results until this completes.
                        </p>
                    </div>
                </div>
            )}

            {!isBlocking && bannerJobs.map(job => (
                <div key={job.id} className="border-b border-amber-200 bg-amber-50/50 px-4 py-2 flex items-center gap-3 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin text-amber-600 shrink-0" />
                    <span className="font-medium text-amber-900">
                        {JOB_TYPE_LABELS[job.type] || job.type}:
                    </span>
                    <span className="text-amber-800 truncate flex-1">
                        {job.current_player || 'Running...'}
                    </span>
                    <span className="text-xs text-amber-600 shrink-0">
                        {job.progress || 0}/{job.total || '?'}
                    </span>
                    <button onClick={() => dismiss(job.id)} className="p-1 hover:bg-amber-100 rounded" aria-label="Dismiss">
                        <X className="h-3 w-3 text-amber-600" />
                    </button>
                </div>
            ))}
        </>
    )
}
