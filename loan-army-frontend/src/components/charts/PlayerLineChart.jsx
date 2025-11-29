import React from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

const STAT_COLORS = {
  goals: '#10b981',
  assists: '#3b82f6',
  rating: '#f59e0b',
  minutes: '#6b7280',
  shots_total: '#ef4444',
  shots_on: '#ec4899',
  passes_total: '#8b5cf6',
  passes_key: '#14b8a6',
  tackles_total: '#f97316',
  duels_won: '#06b6d4',
  saves: '#84cc16',
}

const STAT_LABELS = {
  goals: 'Goals',
  assists: 'Assists',
  rating: 'Rating',
  minutes: 'Minutes',
  shots_total: 'Shots',
  shots_on: 'On Target',
  passes_total: 'Passes',
  passes_key: 'Key Passes',
  tackles_total: 'Tackles',
  duels_won: 'Duels Won',
  saves: 'Saves',
}

export function PlayerLineChart({ data }) {
  const chartData = data?.data || []
  const statKeys = data?.stat_keys || []
  
  if (!chartData.length) {
    return (
      <div className="text-center text-gray-500 py-4 text-sm">
        No data available for line chart
      </div>
    )
  }
  
  // Format dates for display
  const formattedData = chartData.map((item) => ({
    ...item,
    displayDate: item.date 
      ? new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : 'N/A',
  }))
  
  return (
    <div className="space-y-2">
      {data?.player?.name && (
        <div className="text-sm font-medium text-gray-700">
          {data.player.name} - Stats Over Time
        </div>
      )}
      
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={formattedData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis 
              dataKey="displayDate" 
              tick={{ fontSize: 10, fill: '#6b7280' }}
            />
            <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'white',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
              }}
              labelFormatter={(value, payload) => {
                if (payload?.[0]?.payload?.match) {
                  return payload[0].payload.match
                }
                return value
              }}
            />
            <Legend 
              wrapperStyle={{ fontSize: 11, paddingTop: 10 }}
              iconType="circle"
              iconSize={8}
            />
            {statKeys.map((key) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={STAT_LABELS[key] || key.replace('_', ' ')}
                stroke={STAT_COLORS[key] || '#6b7280'}
                strokeWidth={2}
                dot={{ r: 4, fill: STAT_COLORS[key] || '#6b7280' }}
                activeDot={{ r: 6 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export default PlayerLineChart

