import React, { useRef, useEffect } from 'react'
import { ArrowRight, Star } from 'lucide-react'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useJourney } from '@/contexts/JourneyContext'
import { LEVEL_COLORS } from '@/lib/journey-utils'

/**
 * Horizontal career journey strip — replaces JourneyMap.
 * Shows one node per club (stop-level, not season-level) with logos,
 * names, years, level badges, and stats connected by colored lines.
 * Reads from JourneyContext directly (no props needed).
 */
export function JourneyStrip() {
    const { journeyData, progressionNodes, selectedNode, selectNode } = useJourney()
    const scrollRef = useRef(null)
    const selectedStopRef = useRef(null)

    const stops = journeyData?.stops || []

    // Auto-scroll to the selected stop
    useEffect(() => {
        if (selectedStopRef.current && scrollRef.current) {
            selectedStopRef.current.scrollIntoView({
                behavior: 'smooth',
                inline: 'center',
                block: 'nearest',
            })
        }
    }, [selectedNode])

    if (!stops.length) return null

    /** Which stop index is currently selected? */
    const selectedStopIndex = selectedNode?.stopIndex ?? null

    /** Is a stop at or before the selected node? */
    const isStopVisited = (stopIndex) => {
        if (selectedStopIndex == null) return true
        return stopIndex <= selectedStopIndex
    }

    /** Click handler — find the first progressionNode matching this stop and select it. */
    const handleStopClick = (stopIndex) => {
        const isAlreadySelected = selectedStopIndex === stopIndex
        if (isAlreadySelected && selectedNode) {
            selectNode(null)
            return
        }
        const matchNode = progressionNodes.find(n => n.stopIndex === stopIndex)
        if (matchNode) selectNode(matchNode)
    }

    // Collect unique levels across all stops for the legend
    const allLevels = [...new Set(stops.flatMap(s => s.levels || []))]
    const legendLevels = allLevels.filter(l => LEVEL_COLORS[l])

    return (
        <Card className="w-full overflow-hidden">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                    <ArrowRight className="h-5 w-5" />
                    Career Journey
                    {selectedNode && (
                        <Badge variant="outline" className="text-xs ml-2 bg-blue-50 text-blue-700 border-blue-200">
                            {selectedNode.years} — {selectedNode.clubName}
                        </Badge>
                    )}
                </CardTitle>
            </CardHeader>
            <CardContent className="pb-4">
                {/* Scrollable strip */}
                <div
                    ref={scrollRef}
                    className="flex items-start gap-0 overflow-x-auto scrollbar-hide pb-2"
                >
                    {stops.map((stop, index) => {
                        const isFirst = index === 0
                        const isLast = index === stops.length - 1
                        const isSelected = selectedStopIndex === index
                        const visited = isStopVisited(index)
                        const primaryLevel = stop.levels?.[0] || 'First Team'
                        const color = LEVEL_COLORS[primaryLevel] || '#6b7280'

                        // Line color is based on the destination stop's primary level
                        const nextStop = stops[index + 1]
                        const nextLevel = nextStop?.levels?.[0] || 'First Team'
                        const lineColor = LEVEL_COLORS[nextLevel] || '#6b7280'

                        const totalApps = stop.total_apps || 0
                        const totalGoals = stop.total_goals || 0
                        const totalAssists = stop.total_assists || 0

                        return (
                            <div key={`${stop.club_id}-${index}`} className="flex items-start flex-shrink-0">
                                {/* Stop node */}
                                <button
                                    ref={isSelected ? selectedStopRef : null}
                                    onClick={() => handleStopClick(index)}
                                    className={`flex flex-col items-center text-center min-w-[110px] max-w-[130px] px-2 py-2 rounded-lg transition-all duration-200 cursor-pointer ${
                                        isSelected
                                            ? 'bg-blue-50 ring-2 ring-blue-400 ring-offset-1'
                                            : visited
                                                ? 'hover:bg-gray-50'
                                                : 'opacity-40 hover:opacity-60'
                                    }`}
                                >
                                    {/* Logo */}
                                    <div className="relative">
                                        <Avatar className="h-10 w-10 mb-1.5">
                                            <AvatarImage src={stop.club_logo} alt={stop.club_name} />
                                            <AvatarFallback
                                                className="text-xs font-bold text-white"
                                                style={{ backgroundColor: color }}
                                            >
                                                {stop.club_name?.charAt(0) || '?'}
                                            </AvatarFallback>
                                        </Avatar>
                                        {isLast && (
                                            <Star className="absolute -top-1 -right-1 h-3.5 w-3.5 text-amber-500 fill-amber-500" />
                                        )}
                                    </div>

                                    {/* Club name */}
                                    <span className="text-xs font-semibold leading-tight truncate w-full">
                                        {stop.club_name}
                                    </span>

                                    {/* Years */}
                                    <span className="text-[10px] text-gray-500 mt-0.5">
                                        {stop.years}
                                    </span>

                                    {/* Level badges */}
                                    <div className="flex flex-wrap justify-center gap-0.5 mt-1">
                                        {(stop.levels || [primaryLevel]).map((level, idx) => (
                                            <Badge
                                                key={idx}
                                                className="text-[9px] text-white px-1 py-0 leading-tight"
                                                style={{ backgroundColor: LEVEL_COLORS[level] || '#6b7280' }}
                                            >
                                                {level}
                                            </Badge>
                                        ))}
                                    </div>

                                    {/* Stats */}
                                    <span className="text-[10px] text-gray-500 mt-1">
                                        {totalApps} apps
                                        {totalGoals > 0 && <> &middot; {totalGoals}G</>}
                                        {totalAssists > 0 && <> &middot; {totalAssists}A</>}
                                    </span>

                                    {/* Origin / Current badge */}
                                    {isFirst && (
                                        <Badge variant="outline" className="text-[9px] mt-1 px-1 py-0 border-purple-300 text-purple-600">
                                            Origin
                                        </Badge>
                                    )}
                                    {isLast && !isFirst && (
                                        <Badge variant="outline" className="text-[9px] mt-1 px-1 py-0 border-green-300 text-green-600">
                                            Current
                                        </Badge>
                                    )}
                                </button>

                                {/* Connecting line to next stop */}
                                {!isLast && (
                                    <div className="flex items-center self-center mt-5">
                                        <div
                                            className="h-0.5 transition-all duration-300"
                                            style={isStopVisited(index + 1)
                                                ? { width: '32px', backgroundColor: lineColor, opacity: 0.8 }
                                                : { width: '32px', backgroundImage: `repeating-linear-gradient(90deg, #d1d5db 0px, #d1d5db 4px, transparent 4px, transparent 8px)`, opacity: 0.5 }
                                            }
                                        />
                                    </div>
                                )}
                            </div>
                        )
                    })}
                </div>

                {/* Legend */}
                {legendLevels.length > 0 && (
                    <div className="flex flex-wrap gap-3 mt-2 pt-2 border-t border-gray-100 text-xs text-gray-500">
                        {legendLevels.map(level => (
                            <div key={level} className="flex items-center gap-1">
                                <div
                                    className="w-3 h-0.5 rounded"
                                    style={{ backgroundColor: LEVEL_COLORS[level] }}
                                />
                                <span>{level}</span>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

export default JourneyStrip
