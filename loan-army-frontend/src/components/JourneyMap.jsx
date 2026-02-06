import React, { useState, useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription } from '@/components/ui/drawer'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Loader2, MapPin, Calendar, Target, Trophy, Users } from 'lucide-react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Fix Leaflet marker icons (common issue with bundlers)
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
    iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
})

// Custom marker icons
const createCustomIcon = (color, isOrigin = false, isCurrent = false) => {
    const size = isCurrent ? 35 : isOrigin ? 30 : 25
    return L.divIcon({
        className: 'custom-marker',
        html: `
            <div style="
                background-color: ${color};
                width: ${size}px;
                height: ${size}px;
                border-radius: 50%;
                border: 3px solid white;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                display: flex;
                align-items: center;
                justify-content: center;
                ${isCurrent ? 'animation: pulse 2s infinite;' : ''}
            ">
                ${isOrigin ? '<span style="color:white;font-size:12px;font-weight:bold;">1</span>' : ''}
                ${isCurrent ? '<span style="color:white;font-size:10px;">★</span>' : ''}
            </div>
        `,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
    })
}

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

// Component to auto-fit map bounds
function FitBounds({ stops }) {
    const map = useMap()
    
    React.useEffect(() => {
        if (stops.length > 0) {
            const validStops = stops.filter(s => s.lat && s.lng)
            if (validStops.length > 0) {
                const bounds = L.latLngBounds(validStops.map(s => [s.lat, s.lng]))
                map.fitBounds(bounds, { padding: [50, 50] })
            }
        }
    }, [stops, map])
    
    return null
}

export function JourneyMap({ journeyData, loading, error }) {
    const [selectedStop, setSelectedStop] = useState(null)
    
    // Process journey data for map display
    const { stops, path, center } = useMemo(() => {
        if (!journeyData?.stops) {
            return { stops: [], path: [], center: [51.5, -0.1] }
        }
        
        const validStops = journeyData.stops.filter(s => s.lat && s.lng)
        const pathCoords = validStops.map(s => [s.lat, s.lng])
        
        // Calculate center
        let centerLat = 51.5, centerLng = -0.1
        if (validStops.length > 0) {
            centerLat = validStops.reduce((sum, s) => sum + s.lat, 0) / validStops.length
            centerLng = validStops.reduce((sum, s) => sum + s.lng, 0) / validStops.length
        }
        
        return {
            stops: journeyData.stops,
            path: pathCoords,
            center: [centerLat, centerLng]
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
                        <MapContainer
                            center={center}
                            zoom={4}
                            style={{ height: '100%', width: '100%' }}
                            scrollWheelZoom={true}
                        >
                            <TileLayer
                                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                            />
                            
                            <FitBounds stops={validStops} />
                            
                            {/* Journey path line */}
                            {path.length > 1 && (
                                <Polyline
                                    positions={path}
                                    pathOptions={{
                                        color: '#3b82f6',
                                        weight: 3,
                                        opacity: 0.7,
                                        dashArray: '10, 10'
                                    }}
                                />
                            )}
                            
                            {/* Club markers */}
                            {validStops.map((stop, index) => {
                                const isOrigin = index === 0
                                const isCurrent = index === validStops.length - 1
                                const primaryLevel = stop.levels?.[0] || 'First Team'
                                const color = LEVEL_COLORS[primaryLevel] || '#6b7280'
                                
                                return (
                                    <Marker
                                        key={stop.club_id}
                                        position={[stop.lat, stop.lng]}
                                        icon={createCustomIcon(color, isOrigin, isCurrent)}
                                        eventHandlers={{
                                            click: () => setSelectedStop(stop)
                                        }}
                                    >
                                        <Popup>
                                            <div className="text-sm">
                                                <strong>{stop.club_name}</strong>
                                                <br />
                                                {stop.years}
                                                <br />
                                                {stop.total_apps} apps, {stop.total_goals} goals
                                            </div>
                                        </Popup>
                                    </Marker>
                                )
                            })}
                        </MapContainer>
                        
                        {/* Legend */}
                        <div className="absolute bottom-2 left-2 bg-white/90 rounded-lg p-2 text-xs shadow-md z-[1000]">
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
                                    {selectedStop?.city && ` • ${selectedStop.city}`}
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
                                                    {stats.apps} apps • {stats.goals}G • {stats.assists}A
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
            
            {/* CSS for pulse animation */}
            <style>{`
                @keyframes pulse {
                    0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
                    70% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
                    100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
                }
            `}</style>
        </>
    )
}

export default JourneyMap
