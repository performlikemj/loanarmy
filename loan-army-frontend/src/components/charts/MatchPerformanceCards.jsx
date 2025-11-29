import React from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { 
  Clock, Target, Users, Trophy, AlertTriangle, 
  Star, Footprints, Shield
} from 'lucide-react'

function StatBadge({ icon: Icon, label, value, highlight = false }) {
  if (value === null || value === undefined) return null
  
  return (
    <div className={cn(
      'flex items-center gap-1 text-xs px-2 py-1 rounded-md',
      highlight ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-700'
    )}>
      <Icon className="h-3 w-3" />
      <span className="font-medium">{value}</span>
    </div>
  )
}

function MatchCard({ fixture }) {
  const stats = fixture.stats || {}
  const isWin = fixture.is_home 
    ? fixture.home_team.score > fixture.away_team.score
    : fixture.away_team.score > fixture.home_team.score
  const isDraw = fixture.home_team.score === fixture.away_team.score
  
  return (
    <Card className={cn(
      'overflow-hidden border-l-4',
      isWin ? 'border-l-green-500' : isDraw ? 'border-l-gray-400' : 'border-l-red-500'
    )}>
      <CardContent className="p-3">
        {/* Match header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            {/* Home team */}
            <div className="flex items-center gap-1">
              {fixture.home_team.logo && (
                <img 
                  src={fixture.home_team.logo} 
                  alt={fixture.home_team.name}
                  className="h-5 w-5 object-contain"
                />
              )}
              <span className={cn(
                'text-sm font-medium',
                fixture.is_home && 'font-bold'
              )}>
                {fixture.home_team.name}
              </span>
            </div>
            
            {/* Score */}
            <div className="text-lg font-bold px-2">
              {fixture.home_team.score} - {fixture.away_team.score}
            </div>
            
            {/* Away team */}
            <div className="flex items-center gap-1">
              <span className={cn(
                'text-sm font-medium',
                !fixture.is_home && 'font-bold'
              )}>
                {fixture.away_team.name}
              </span>
              {fixture.away_team.logo && (
                <img 
                  src={fixture.away_team.logo} 
                  alt={fixture.away_team.name}
                  className="h-5 w-5 object-contain"
                />
              )}
            </div>
          </div>
          
          {/* Competition & date */}
          <div className="text-right text-xs text-gray-500">
            <div>{fixture.competition}</div>
            <div>{new Date(fixture.date).toLocaleDateString()}</div>
          </div>
        </div>
        
        {/* Player stats */}
        <div className="flex flex-wrap gap-2">
          <StatBadge icon={Clock} value={`${stats.minutes}'`} />
          {stats.rating && (
            <StatBadge 
              icon={Star} 
              value={stats.rating?.toFixed(1)} 
              highlight={stats.rating >= 7}
            />
          )}
          {stats.goals > 0 && (
            <StatBadge icon={Target} value={`${stats.goals} Goal${stats.goals > 1 ? 's' : ''}`} highlight />
          )}
          {stats.assists > 0 && (
            <StatBadge icon={Users} value={`${stats.assists} Assist${stats.assists > 1 ? 's' : ''}`} highlight />
          )}
          {stats.yellows > 0 && (
            <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200 text-xs">
              {stats.yellows} Yellow
            </Badge>
          )}
          {stats.reds > 0 && (
            <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 text-xs">
              Red Card
            </Badge>
          )}
        </div>
        
        {/* Extended stats row */}
        <div className="flex flex-wrap gap-2 mt-2 text-xs text-gray-600">
          {stats.shots?.total > 0 && (
            <span>Shots: {stats.shots.on_target}/{stats.shots.total}</span>
          )}
          {stats.passes?.total > 0 && (
            <span>Passes: {stats.passes.total} ({stats.passes.accuracy})</span>
          )}
          {stats.tackles?.total > 0 && (
            <span>Tackles: {stats.tackles.total}</span>
          )}
          {stats.duels?.total > 0 && (
            <span>Duels: {stats.duels.won}/{stats.duels.total}</span>
          )}
          {stats.saves > 0 && (
            <span>Saves: {stats.saves}</span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function MatchPerformanceCards({ data }) {
  const fixtures = data?.fixtures || []
  
  if (!fixtures.length) {
    return (
      <div className="text-center text-gray-500 py-4 text-sm">
        No matches found for this period
      </div>
    )
  }
  
  return (
    <div className="space-y-3">
      {data?.player?.name && (
        <div className="text-sm font-medium text-gray-700 mb-2">
          {data.player.name} - {fixtures.length} match{fixtures.length !== 1 ? 'es' : ''}
        </div>
      )}
      {fixtures.map((fixture, idx) => (
        <MatchCard key={fixture.fixture_id || idx} fixture={fixture} />
      ))}
    </div>
  )
}

export default MatchPerformanceCards

