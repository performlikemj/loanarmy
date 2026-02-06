import React, { useState, useMemo } from 'react'
import {
    ComposableMap, Geographies, Geography, Marker, Line, ZoomableGroup,
} from 'react-simple-maps'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription } from '@/components/ui/drawer'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Loader2, MapPin, Calendar } from 'lucide-react'

const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json'

// Level colors
const LEVEL_COLORS = {
    'U18': '#9333ea',      // Purple
    'U19': '#8b5cf6',      // Violet
    'U21': '#6366f1',      // Indigo
    'U23': '#3b82f6',      // Blue
    'Reserve': '#06b6d4',  // Cyan
    'First Team': '#22c55e', // Green
    'International': '#f59e0b', // Amber
    'International Youth': '#d946ef', // Fuchsia
}

/**
 * Calculate zoom center and level from an array of stops.
 * react-simple-maps coordinates are [lng, lat].
 */
function calculateView(stops) {
    const valid = stops.filter(s => s.lat && s.lng)
    if (valid.length === 0) return { center: [0, 30], zoom: 1 }

    const lats = valid.map(s => s.lat)
    const lngs = valid.map(s => s.lng)

    const centerLat = (Math.min(...lats) + Math.max(...lats)) / 2
    const centerLng = (Math.min(...lngs) + Math.max(...lngs)) / 2

    const span = Math.max(
        Math.max(...lats) - Math.min(...lats),
        Math.max(...lngs) - Math.min(...lngs),
        5,
    )

    let zoom = 1
    if (span < 5) zoom = 6
    else if (span < 15) zoom = 4
    else if (span < 30) zoom = 3
    else if (span < 60) zoom = 2

    return { center: [centerLng, centerLat], zoom }
}

export function JourneyMap({ journeyData, loading, error }) {
    const [selectedStop, setSelectedStop] = useState(null)

    const { stops, pathPairs, view } = useMemo(() => {
        if (!journeyData?.stops) {
            return { stops: [], pathPairs: [], view: { center: [0, 30], zoom: 1 } }
        }

        const validStops = journeyData.stops.filter(s => s.lat && s.lng)

        const pairs = []
        for (let i = 0; i < validStops.length - 1; i++) {
            pairs.push({
                from: [validStops[i].lng, validStops[i].lat],
                to: [validStops[i + 1].lng, validStops[i + 1].lat],
            })
        }

        return {
            stops: journeyData.stops,
            pathPairs: pairs,
            view: calculateView(validStops),
        }
    }, [journeyData])

    if (loading) {
        return (
            <Card className="w-full h-[400px] flex items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </Card>
        )
    }

    if (error) {
        return (
            <Card className="w-full h-[400px] flex items-center justify-center">
                <p className="text-muted-foreground">Failed to load journey data</p>
            </Card>
        )
    }

    if (!journeyData || stops.length === 0) {
        return (
            <Card className="w-full h-[400px] flex items-center justify-center">
                <div className="text-center">
                    <MapPin className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                    <p className="text-muted-foreground">No journey data available</p>
                </div>
            </Card>
        )
    }

    const validStops = stops.filter(s => s.lat && s.lng)

    return (
        <>
            <Card className="w-full overflow-hidden">
                <CardHeader className="pb-2">
                    <CardTitle className="text-lg flex items-center gap-2">
                        <MapPin className="h-5 w-5" />
                        Career Journey
                    </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="h-[400px] w-full relative">
                        <ComposableMap
                            projection="geoMercator"
                            projectionConfig={{ scale: 150 }}
                            style={{ width: '100%', height: '100%' }}
                        >
                            <ZoomableGroup center={view.center} zoom={view.zoom}>
                                <Geographies geography={GEO_URL}>
                                    {({ geographies }) =>
                                        geographies.map((geo) => (
                                            <Geography
                                                key={geo.rsmKey}
                                                geography={geo}
                                                fill="#e5e7eb"
                                                stroke="#d1d5db"
                                                strokeWidth={0.5}
                                                style={{
                                                    default: { outline: 'none' },
                                                    hover: { outline: 'none', fill: '#d1d5db' },
                                                    pressed: { outline: 'none' },
                                                }}
                                            />
                                        ))
                                    }
                                </Geographies>

                                {/* Journey path lines */}
                                {pathPairs.map((pair, i) => (
                                    <Line
                                        key={i}
                                        from={pair.from}
                                        to={pair.to}
                                        stroke="#3b82f6"
                                        strokeWidth={2}
                                        strokeLinecap="round"
                                        strokeDasharray="5,5"
                                        strokeOpacity={0.7}
                                    />
                                ))}

                                {/* Club markers */}
                                {validStops.map((stop, index) => {
                                    const isOrigin = index === 0
                                    const isCurrent = index === validStops.length - 1
                                    const primaryLevel = stop.levels?.[0] || 'First Team'
                                    const color = LEVEL_COLORS[primaryLevel] || '#6b7280'
                                    const r = isCurrent ? 8 : isOrigin ? 7 : 5

                                    return (
                                        <Marker
                                            key={`${stop.club_id}-${index}`}
                                            coordinates={[stop.lng, stop.lat]}
                                        >
                                            <circle
                                                r={r}
                                                fill={color}
                                                stroke="white"
                                                strokeWidth={2}
                                                style={{ cursor: 'pointer' }}
                                                onClick={() => setSelectedStop(stop)}
                                            />
                                            {isOrigin && (
                                                <text
                                                    textAnchor="middle"
                                                    y={4}
                                                    style={{ fontSize: '7px', fill: 'white', fontWeight: 'bold', pointerEvents: 'none' }}
                                                >
                                                    1
                                                </text>
                                            )}
                                            {isCurrent && (
                                                <text
                                                    textAnchor="middle"
                                                    y={3}
                                                    style={{ fontSize: '7px', fill: 'white', pointerEvents: 'none' }}
                                                >
                                                    ★
                                                </text>
                                            )}
                                        </Marker>
                                    )
                                })}
                            </ZoomableGroup>
                        </ComposableMap>

                        {/* Legend */}
                        <div className="absolute bottom-2 left-2 bg-white/90 rounded-lg p-2 text-xs shadow-md z-10">
                            <div className="flex flex-wrap gap-2">
                                <div className="flex items-center gap-1">
                                    <div className="w-3 h-3 rounded-full bg-purple-500" />
                                    <span>Youth</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <div className="w-3 h-3 rounded-full bg-green-500" />
                                    <span>First Team</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <div className="w-3 h-3 rounded-full bg-amber-500" />
                                    <span>International</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Stop Detail Drawer */}
            <Drawer open={!!selectedStop} onOpenChange={(open) => !open && setSelectedStop(null)}>
                <DrawerContent>
                    <DrawerHeader>
                        <div className="flex items-center gap-3">
                            {selectedStop?.club_logo && (
                                <Avatar className="h-12 w-12">
                                    <AvatarImage src={selectedStop.club_logo} alt={selectedStop?.club_name} />
                                    <AvatarFallback>{selectedStop?.club_name?.[0]}</AvatarFallback>
                                </Avatar>
                            )}
                            <div>
                                <DrawerTitle>{selectedStop?.club_name}</DrawerTitle>
                                <DrawerDescription className="flex items-center gap-1">
                                    <Calendar className="h-3 w-3" />
                                    {selectedStop?.years}
                                    {selectedStop?.city && ` \u2022 ${selectedStop.city}`}
                                    {selectedStop?.country && `, ${selectedStop.country}`}
                                </DrawerDescription>
                            </div>
                        </div>
                    </DrawerHeader>

                    <div className="p-4 space-y-4">
                        {/* Levels */}
                        <div>
                            <h4 className="text-sm font-medium text-muted-foreground mb-2">Levels</h4>
                            <div className="flex flex-wrap gap-2">
                                {selectedStop?.levels?.map(level => (
                                    <Badge
                                        key={level}
                                        style={{ backgroundColor: LEVEL_COLORS[level] || '#6b7280' }}
                                        className="text-white"
                                    >
                                        {level}
                                    </Badge>
                                ))}
                            </div>
                        </div>

                        {/* Stats Summary */}
                        <div className="grid grid-cols-3 gap-4">
                            <div className="text-center p-3 bg-muted rounded-lg">
                                <div className="text-2xl font-bold">{selectedStop?.total_apps || 0}</div>
                                <div className="text-xs text-muted-foreground">Appearances</div>
                            </div>
                            <div className="text-center p-3 bg-muted rounded-lg">
                                <div className="text-2xl font-bold">{selectedStop?.total_goals || 0}</div>
                                <div className="text-xs text-muted-foreground">Goals</div>
                            </div>
                            <div className="text-center p-3 bg-muted rounded-lg">
                                <div className="text-2xl font-bold">{selectedStop?.total_assists || 0}</div>
                                <div className="text-xs text-muted-foreground">Assists</div>
                            </div>
                        </div>

                        {/* Level Breakdown */}
                        {selectedStop?.breakdown && Object.keys(selectedStop.breakdown).length > 0 && (
                            <div>
                                <h4 className="text-sm font-medium text-muted-foreground mb-2">By Level</h4>
                                <div className="space-y-2">
                                    {Object.entries(selectedStop.breakdown)
                                        .sort(([a], [b]) => (LEVEL_COLORS[b] ? 1 : 0) - (LEVEL_COLORS[a] ? 1 : 0))
                                        .map(([level, stats]) => (
                                            <div key={level} className="flex items-center justify-between p-2 bg-muted/50 rounded">
                                                <Badge
                                                    variant="outline"
                                                    style={{ borderColor: LEVEL_COLORS[level] || '#6b7280', color: LEVEL_COLORS[level] || '#6b7280' }}
                                                >
                                                    {level}
                                                </Badge>
                                                <span className="text-sm">
                                                    {stats.apps} apps &bull; {stats.goals}G &bull; {stats.assists}A
                                                </span>
                                            </div>
                                        ))
                                    }
                                </div>
                            </div>
                        )}

                        {/* Competitions */}
                        {selectedStop?.competitions?.length > 0 && (
                            <div>
                                <h4 className="text-sm font-medium text-muted-foreground mb-2">Competitions</h4>
                                <ScrollArea className="h-[200px]">
                                    <div className="space-y-2">
                                        {selectedStop.competitions.map((comp, idx) => (
                                            <div key={idx} className="flex items-center justify-between p-2 border rounded text-sm">
                                                <div>
                                                    <div className="font-medium">{comp.league}</div>
                                                    <div className="text-xs text-muted-foreground">{comp.season}/{comp.season + 1}</div>
                                                </div>
                                                <div className="text-right">
                                                    <div>{comp.apps} apps</div>
                                                    <div className="text-xs text-muted-foreground">
                                                        {comp.goals}G {comp.assists}A
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </ScrollArea>
                            </div>
                        )}
                    </div>
                </DrawerContent>
            </Drawer>
        </>
    )
}

export default JourneyMap
