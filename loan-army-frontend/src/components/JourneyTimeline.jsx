import React from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Loader2, MapPin, Star, Flag, Trophy, TrendingUp } from 'lucide-react'

// Level colors matching the map
const LEVEL_COLORS = {
    'U18': '#9333ea',
    'U19': '#8b5cf6',
    'U21': '#6366f1',
    'U23': '#3b82f6',
    'Reserve': '#06b6d4',
    'First Team': '#22c55e',
    'International': '#f59e0b',
    'International Youth': '#d946ef',
}

const LEVEL_ICONS = {
    'U18': '🌱',
    'U19': '🌿',
    'U21': '🌳',
    'U23': '🌲',
    'Reserve': '📋',
    'First Team': '⭐',
    'International': '🌍',
    'International Youth': '🏆',
}

export function JourneyTimeline({ journeyData, loading, error }) {
    if (loading) {
        return (
            <Card className="w-full">
                <CardContent className="flex items-center justify-center py-8">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </CardContent>
            </Card>
        )
    }
    
    if (error) {
        return (
            <Card className="w-full">
                <CardContent className="flex items-center justify-center py-8">
                    <p className="text-muted-foreground">Failed to load journey data</p>
                </CardContent>
            </Card>
        )
    }
    
    if (!journeyData?.stops || journeyData.stops.length === 0) {
        return (
            <Card className="w-full">
                <CardContent className="flex items-center justify-center py-8">
                    <div className="text-center">
                        <MapPin className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                        <p className="text-muted-foreground">No journey data available</p>
                    </div>
                </CardContent>
            </Card>
        )
    }
    
    const { stops } = journeyData
    
    return (
        <Card className="w-full">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                    <TrendingUp className="h-5 w-5" />
                    Career Timeline
                </CardTitle>
            </CardHeader>
            <CardContent>
                <ScrollArea className="h-[400px] pr-4">
                    <div className="relative">
                        {/* Timeline line */}
                        <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-border" />
                        
                        {/* Timeline entries */}
                        <div className="space-y-6">
                            {stops.map((stop, index) => {
                                const isFirst = index === 0
                                const isLast = index === stops.length - 1
                                const primaryLevel = stop.levels?.[0] || 'First Team'
                                const color = LEVEL_COLORS[primaryLevel] || '#6b7280'
                                
                                return (
                                    <div key={stop.club_id} className="relative pl-16">
                                        {/* Timeline dot */}
                                        <div 
                                            className="absolute left-4 w-5 h-5 rounded-full border-2 border-white shadow-md flex items-center justify-center text-xs"
                                            style={{ backgroundColor: color }}
                                        >
                                            {isFirst && '1'}
                                            {isLast && !isFirst && '★'}
                                        </div>
                                        
                                        {/* Content card */}
                                        <div className={`p-3 rounded-lg border ${isLast ? 'bg-green-50 border-green-200 dark:bg-green-950/20' : 'bg-card'}`}>
                                            {/* Header */}
                                            <div className="flex items-start gap-3">
                                                {stop.club_logo && (
                                                    <Avatar className="h-10 w-10">
                                                        <AvatarImage src={stop.club_logo} alt={stop.club_name} />
                                                        <AvatarFallback>{stop.club_name?.[0]}</AvatarFallback>
                                                    </Avatar>
                                                )}
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                        <h4 className="font-semibold truncate">{stop.club_name}</h4>
                                                        {isFirst && (
                                                            <Badge variant="outline" className="text-xs">
                                                                <Flag className="h-3 w-3 mr-1" />
                                                                Origin
                                                            </Badge>
                                                        )}
                                                        {isLast && (
                                                            <Badge className="bg-green-500 text-xs">
                                                                <Star className="h-3 w-3 mr-1" />
                                                                Current
                                                            </Badge>
                                                        )}
                                                    </div>
                                                    <p className="text-sm text-muted-foreground">
                                                        {stop.years}
                                                        {stop.city && ` • ${stop.city}`}
                                                    </p>
                                                </div>
                                            </div>
                                            
                                            {/* Levels */}
                                            <div className="flex flex-wrap gap-1 mt-2">
                                                {stop.levels?.map(level => (
                                                    <Badge 
                                                        key={level}
                                                        variant="secondary"
                                                        className="text-xs"
                                                        style={{ 
                                                            backgroundColor: `${LEVEL_COLORS[level]}20`,
                                                            color: LEVEL_COLORS[level],
                                                            borderColor: LEVEL_COLORS[level]
                                                        }}
                                                    >
                                                        {LEVEL_ICONS[level]} {level}
                                                    </Badge>
                                                ))}
                                            </div>
                                            
                                            {/* Stats */}
                                            <div className="flex gap-4 mt-2 text-sm">
                                                <span>
                                                    <strong>{stop.total_apps}</strong> apps
                                                </span>
                                                <span>
                                                    <strong>{stop.total_goals}</strong> goals
                                                </span>
                                                <span>
                                                    <strong>{stop.total_assists}</strong> assists
                                                </span>
                                            </div>
                                            
                                            {/* Level breakdown (collapsed) */}
                                            {stop.breakdown && Object.keys(stop.breakdown).length > 1 && (
                                                <details className="mt-2">
                                                    <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
                                                        Show breakdown by level
                                                    </summary>
                                                    <div className="mt-2 space-y-1">
                                                        {Object.entries(stop.breakdown).map(([level, stats]) => (
                                                            <div key={level} className="flex items-center justify-between text-xs p-1 bg-muted/50 rounded">
                                                                <span style={{ color: LEVEL_COLORS[level] }}>
                                                                    {LEVEL_ICONS[level]} {level}
                                                                </span>
                                                                <span>
                                                                    {stats.apps} apps • {stats.goals}G • {stats.assists}A
                                                                </span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </details>
                                            )}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                </ScrollArea>
            </CardContent>
        </Card>
    )
}

export default JourneyTimeline
