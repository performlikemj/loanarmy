import { useState, useEffect, useMemo } from 'react';
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  Line,
} from 'react-simple-maps';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

// World map topology (using a simplified world map)
const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';

// Country-specific map configurations for optimal viewing
const COUNTRY_CONFIGS = {
  England: { center: [-1.5, 52.5], scale: 3000 },
  Scotland: { center: [-4.0, 56.5], scale: 4000 },
  Wales: { center: [-3.5, 52.0], scale: 5000 },
  'Northern Ireland': { center: [-6.5, 54.6], scale: 8000 },
  Ireland: { center: [-8.0, 53.5], scale: 4000 },
  Netherlands: { center: [5.3, 52.2], scale: 5000 },
  Belgium: { center: [4.5, 50.5], scale: 6000 },
  France: { center: [2.5, 46.5], scale: 1800 },
  Germany: { center: [10.5, 51.0], scale: 2200 },
  Spain: { center: [-3.5, 40.0], scale: 2000 },
  Portugal: { center: [-8.0, 39.5], scale: 3500 },
  Italy: { center: [12.5, 42.5], scale: 2000 },
  Austria: { center: [14.0, 47.5], scale: 4000 },
  Switzerland: { center: [8.2, 46.8], scale: 6000 },
  Denmark: { center: [10.0, 56.0], scale: 4000 },
  Sweden: { center: [15.0, 62.0], scale: 1200 },
  Norway: { center: [10.0, 64.0], scale: 1000 },
  Finland: { center: [26.0, 64.0], scale: 1200 },
  Poland: { center: [19.0, 52.0], scale: 2500 },
  'Czech Republic': { center: [15.5, 49.8], scale: 4500 },
  Greece: { center: [22.0, 39.0], scale: 3000 },
  Turkey: { center: [35.0, 39.0], scale: 1800 },
  USA: { center: [-98.0, 39.0], scale: 600 },
  Canada: { center: [-95.0, 56.0], scale: 400 },
  Australia: { center: [134.0, -25.0], scale: 600 },
  Brazil: { center: [-52.0, -14.0], scale: 500 },
  Argentina: { center: [-64.0, -34.0], scale: 700 },
  Japan: { center: [138.0, 36.0], scale: 1500 },
  'South Korea': { center: [128.0, 36.0], scale: 4000 },
  China: { center: [105.0, 35.0], scale: 500 },
};

// Stint type colors
const STINT_COLORS = {
  academy: '#3b82f6', // blue
  loan: '#f97316', // orange
  first_team: '#22c55e', // green
  permanent_transfer: '#8b5cf6', // purple
  moved_on: '#6b7280', // gray for players who left
};

const STINT_LABELS = {
  academy: 'Academy',
  loan: 'Loan',
  first_team: 'First Team',
  permanent_transfer: 'Transfer',
  moved_on: 'Moved On',
};

export default function PlayerJourneyMap({
  playerId,
  loanedPlayerId,
  stints: propStints,
  className = '',
}) {
  const [stints, setStints] = useState(propStints || []);
  const [loading, setLoading] = useState(!propStints);
  const [error, setError] = useState(null);
  const [hoveredStint, setHoveredStint] = useState(null);
  const [selectedCountry, setSelectedCountry] = useState(null);
  const [countries, setCountries] = useState([]);
  const [isMultiCountry, setIsMultiCountry] = useState(false);
  const [movedOn, setMovedOn] = useState(false);

  // Fetch journey data if not provided as props
  useEffect(() => {
    if (propStints) {
      setStints(propStints);
      return;
    }

    const fetchJourney = async () => {
      try {
        setLoading(true);
        const endpoint = loanedPlayerId
          ? `/api/loans/${loanedPlayerId}/journey`
          : `/api/players/${playerId}/journey`;

        const response = await fetch(endpoint);
        if (!response.ok) throw new Error('Failed to fetch journey');

        const data = await response.json();
        setStints(data.stints || []);
        setCountries(data.countries || []);
        setIsMultiCountry(data.is_multi_country || false);
        setMovedOn(data.moved_on || false);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (playerId || loanedPlayerId) {
      fetchJourney();
    }
  }, [playerId, loanedPlayerId, propStints]);

  // Filter stints with valid coordinates
  const validStints = useMemo(
    () => stints.filter((s) => s.latitude && s.longitude),
    [stints]
  );

  // Filter stints by selected country (for country deep-dive view)
  const visibleStints = useMemo(() => {
    if (!selectedCountry) return validStints;
    return validStints.filter((s) => s.country === selectedCountry);
  }, [validStints, selectedCountry]);

  // Generate line connections between consecutive stints
  // When viewing all stints, connect in sequence order
  // When viewing a country, only connect stints within that country
  const connections = useMemo(() => {
    const lines = [];
    const stintsToConnect = selectedCountry ? visibleStints : validStints;

    for (let i = 0; i < stintsToConnect.length - 1; i++) {
      const from = stintsToConnect[i];
      const to = stintsToConnect[i + 1];
      lines.push({
        from: [from.longitude, from.latitude],
        to: [to.longitude, to.latitude],
        key: `${from.id}-${to.id}`,
      });
    }
    return lines;
  }, [validStints, visibleStints, selectedCountry]);

  // Calculate map center and scale based on view mode
  const { mapCenter, mapScale } = useMemo(() => {
    // Single country deep-dive: use country config if available
    if (selectedCountry && COUNTRY_CONFIGS[selectedCountry]) {
      const config = COUNTRY_CONFIGS[selectedCountry];
      return { mapCenter: config.center, mapScale: config.scale };
    }

    // If we have visible stints, calculate from their positions
    const stintsForCalc = visibleStints.length > 0 ? visibleStints : validStints;

    if (stintsForCalc.length === 0) {
      return { mapCenter: [0, 30], mapScale: 200 };
    }

    const lngs = stintsForCalc.map((s) => s.longitude);
    const lats = stintsForCalc.map((s) => s.latitude);

    const centerLng = (Math.min(...lngs) + Math.max(...lngs)) / 2;
    const centerLat = (Math.min(...lats) + Math.max(...lats)) / 2;

    // Single country journey (all stints in same country): use country config
    const uniqueCountries = [...new Set(stintsForCalc.map((s) => s.country).filter(Boolean))];
    if (uniqueCountries.length === 1 && COUNTRY_CONFIGS[uniqueCountries[0]]) {
      const config = COUNTRY_CONFIGS[uniqueCountries[0]];
      return { mapCenter: config.center, mapScale: config.scale };
    }

    // Multi-country or unknown country: calculate from spread
    const lngSpread = Math.max(...lngs) - Math.min(...lngs);
    const latSpread = Math.max(...lats) - Math.min(...lats);
    const maxSpread = Math.max(lngSpread, latSpread);

    let scale;
    if (maxSpread < 2) scale = 4000;
    else if (maxSpread < 5) scale = 2500;
    else if (maxSpread < 10) scale = 1500;
    else if (maxSpread < 20) scale = 1000;
    else if (maxSpread < 40) scale = 600;
    else scale = 350;

    return { mapCenter: [centerLng, centerLat], mapScale: scale };
  }, [validStints, visibleStints, selectedCountry]);

  if (loading) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="text-lg">Player Journey</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="text-lg">Player Journey</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Unable to load journey data</p>
        </CardContent>
      </Card>
    );
  }

  if (validStints.length === 0) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="text-lg">Player Journey</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            No journey data available for this player
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          Player Journey
          <span className="text-sm font-normal text-muted-foreground">
            ({validStints.length} stop{validStints.length !== 1 ? 's' : ''})
          </span>
          {movedOn && (
            <Badge variant="secondary" className="ml-auto text-xs">
              Moved On
            </Badge>
          )}
        </CardTitle>
      </CardHeader>

      {/* Country navigation for multi-country journeys */}
      {isMultiCountry && countries.length > 1 && (
        <div className="flex flex-wrap gap-2 px-4 py-2 border-b">
          <Button
            variant={selectedCountry === null ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSelectedCountry(null)}
          >
            Overview
          </Button>
          {countries.map((country) => (
            <Button
              key={country.name}
              variant={selectedCountry === country.name ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSelectedCountry(country.name)}
            >
              {country.name}
              <span className="ml-1 text-xs opacity-70">
                ({country.stint_count})
              </span>
            </Button>
          ))}
        </div>
      )}

      <CardContent className="p-0">
        {/* Map */}
        <div className="relative h-64 w-full overflow-hidden rounded-b-lg bg-slate-900">
          <ComposableMap
            projection="geoMercator"
            projectionConfig={{
              center: mapCenter,
              scale: mapScale,
            }}
            style={{ width: '100%', height: '100%' }}
          >
            <Geographies geography={GEO_URL}>
              {({ geographies }) =>
                geographies.map((geo) => (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill="#1e293b"
                    stroke="#334155"
                    strokeWidth={0.5}
                    style={{
                      default: { outline: 'none' },
                      hover: { outline: 'none', fill: '#334155' },
                      pressed: { outline: 'none' },
                    }}
                  />
                ))
              }
            </Geographies>

            {/* Connection lines (dashed) */}
            {connections.map((conn) => (
              <Line
                key={conn.key}
                from={conn.from}
                to={conn.to}
                stroke="#94a3b8"
                strokeWidth={2}
                strokeDasharray="4 4"
                strokeLinecap="round"
              />
            ))}

            {/* Location markers - show visible stints only */}
            {visibleStints.map((stint) => (
              <Marker
                key={stint.id}
                coordinates={[stint.longitude, stint.latitude]}
                onMouseEnter={() => setHoveredStint(stint)}
                onMouseLeave={() => setHoveredStint(null)}
              >
                {/* Outer ring for sequence number */}
                <circle
                  r={14}
                  fill={STINT_COLORS[stint.stint_type] || '#6b7280'}
                  opacity={0.3}
                />
                {/* Inner circle */}
                <circle
                  r={8}
                  fill={STINT_COLORS[stint.stint_type] || '#6b7280'}
                  stroke="#fff"
                  strokeWidth={2}
                  style={{ cursor: 'pointer' }}
                />
                {/* Sequence number - use original sequence from full journey */}
                <text
                  textAnchor="middle"
                  y={4}
                  style={{
                    fontFamily: 'system-ui',
                    fontSize: 10,
                    fontWeight: 'bold',
                    fill: '#fff',
                    pointerEvents: 'none',
                  }}
                >
                  {stint.sequence}
                </text>
              </Marker>
            ))}
          </ComposableMap>

          {/* Hover tooltip */}
          {hoveredStint && (
            <div className="absolute bottom-2 left-2 bg-black/80 text-white text-xs px-3 py-2 rounded-md">
              <div className="font-semibold">{hoveredStint.team_name}</div>
              <div className="text-slate-300">
                {hoveredStint.city}
                {hoveredStint.country && `, ${hoveredStint.country}`}
              </div>
              <div className="text-slate-400">
                {STINT_LABELS[hoveredStint.stint_type]}
                {hoveredStint.level && ` (${hoveredStint.level})`}
              </div>
            </div>
          )}
        </div>

        {/* Timeline legend below map */}
        <div className="p-4 border-t">
          {/* Show full journey when in overview, or filtered when country selected */}
          <div className="flex flex-wrap gap-2">
            {(selectedCountry ? visibleStints : validStints).map(
              (stint, index, arr) => (
                <div
                  key={stint.id}
                  className="flex items-center gap-2 text-sm"
                  onMouseEnter={() => setHoveredStint(stint)}
                  onMouseLeave={() => setHoveredStint(null)}
                >
                  <Badge
                    variant="outline"
                    className="cursor-pointer"
                    style={{
                      borderColor: STINT_COLORS[stint.stint_type],
                      backgroundColor:
                        hoveredStint?.id === stint.id
                          ? STINT_COLORS[stint.stint_type] + '20'
                          : 'transparent',
                    }}
                  >
                    <span
                      className="w-4 h-4 rounded-full flex items-center justify-center text-xs font-bold mr-1"
                      style={{
                        backgroundColor: STINT_COLORS[stint.stint_type],
                        color: 'white',
                      }}
                    >
                      {stint.sequence}
                    </span>
                    {stint.team_name}
                  </Badge>
                  {index < arr.length - 1 && (
                    <span className="text-muted-foreground">→</span>
                  )}
                </div>
              )
            )}
          </div>

          {/* Date range if available */}
          {validStints.some((s) => s.start_date) && (
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {(selectedCountry ? visibleStints : validStints).map((stint) => (
                <div key={stint.id} className="flex items-center gap-1">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: STINT_COLORS[stint.stint_type] }}
                  />
                  <span>
                    {stint.start_date
                      ? new Date(stint.start_date).getFullYear()
                      : '?'}
                    {stint.end_date
                      ? `-${new Date(stint.end_date).getFullYear()}`
                      : stint.is_current
                        ? '-Present'
                        : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
