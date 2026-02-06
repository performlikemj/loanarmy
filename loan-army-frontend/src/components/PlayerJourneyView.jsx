import React, { useState, useEffect, useRef } from 'react'
import { Loader2, MapPin } from 'lucide-react'
import { APIService } from '@/lib/api'
import { JourneyMap } from './JourneyMap'
import { JourneyTimeline } from './JourneyTimeline'

/**
 * Container component that loads journey data and renders
 * the Leaflet map + timeline.
 *
 * Data flow:
 * 1. Try /api/players/{id}/journey/map (PlayerJourney-based)
 * 2. If 404: retry with ?sync=true to trigger on-demand sync
 * 3. If still fails: fall back to /api/players/{id}/journey (LoanedPlayer-based)
 */
export default function PlayerJourneyView({ playerId }) {
    const [journeyData, setJourneyData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [syncing, setSyncing] = useState(false)
    const abortRef = useRef(false)

    useEffect(() => {
        if (!playerId) return
        abortRef.current = false
        loadJourney()
        return () => { abortRef.current = true }
    }, [playerId])

    const loadJourney = async () => {
        setLoading(true)
        setError(null)

        try {
            // Try the map endpoint first (richer data with coordinates)
            const mapData = await APIService.getPlayerJourneyMap(playerId)
            if (abortRef.current) return
            setJourneyData(mapData)
        } catch (mapErr) {
            if (abortRef.current) return
            // If 404, try syncing, then fall back to old endpoint
            if (mapErr?.status === 404) {
                try {
                    setSyncing(true)
                    // Try with sync=true to trigger on-demand sync
                    const syncedData = await APIService.request(
                        `/players/${playerId}/journey/map?sync=true`
                    )
                    if (abortRef.current) return
                    setJourneyData(syncedData)
                    setSyncing(false)
                } catch {
                    if (abortRef.current) return
                    setSyncing(false)
                    // Final fallback: old LoanedPlayer-based endpoint
                    try {
                        const legacyData = await APIService.getPlayerJourney(playerId)
                        if (abortRef.current) return
                        const transformed = transformStintsToStops(legacyData)
                        setJourneyData(transformed)
                    } catch {
                        if (abortRef.current) return
                        setError('Unable to load journey data')
                    }
                }
            } else {
                setError('Unable to load journey data')
            }
        } finally {
            if (!abortRef.current) {
                setLoading(false)
            }
        }
    }

    if (loading || syncing) {
        return (
            <div className="flex flex-col items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-blue-500 mb-3" />
                <p className="text-sm text-gray-500">
                    {syncing ? 'Building career history...' : 'Loading journey...'}
                </p>
            </div>
        )
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center py-12">
                <MapPin className="h-12 w-12 text-gray-300 mb-2" />
                <p className="text-gray-500">{error}</p>
            </div>
        )
    }

    if (!journeyData) return null

    return (
        <div className="space-y-4">
            <JourneyMap journeyData={journeyData} loading={false} error={null} />
            <JourneyTimeline journeyData={journeyData} loading={false} error={null} />
        </div>
    )
}


/**
 * Transform legacy stint-format data (from /journey endpoint) into
 * the stops format expected by JourneyMap/JourneyTimeline.
 */
function transformStintsToStops(legacyData) {
    const stints = legacyData?.stints || []

    const stops = stints
        .filter(s => s.latitude && s.longitude)
        .map(s => ({
            club_id: s.team_api_id,
            club_name: s.team_name,
            club_logo: s.team_logo,
            lat: s.latitude,
            lng: s.longitude,
            city: s.city,
            country: s.country,
            years: s.years || '',
            levels: s.levels || [s.level || s.stint_type],
            total_apps: s.stats?.apps ?? 0,
            total_goals: s.stats?.goals ?? 0,
            total_assists: s.stats?.assists ?? 0,
            breakdown: s.breakdown || {},
            competitions: s.competitions || [],
        }))

    return {
        player_api_id: legacyData.player_id,
        player_name: legacyData.player_name,
        stops,
    }
}
