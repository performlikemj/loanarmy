import React from 'react'
// eslint-disable-next-line no-unused-vars
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { useJourney } from '@/contexts/JourneyContext'
import { LEVEL_COLORS } from '@/lib/journey-utils'

/**
 * Slides in above the map when a non-current node is selected,
 * showing season-specific stats for that "memory".
 */
export function SeasonStatsPanel() {
    const { selectedNode, selectNode, progressionNodes } = useJourney()

    const isLatest = selectedNode && selectedNode.id === progressionNodes[progressionNodes.length - 1]?.id

    return (
        <AnimatePresence>
            {selectedNode && !isLatest && (
                <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.25, ease: 'easeInOut' }}
                    className="overflow-hidden"
                >
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                        {/* Header row */}
                        <div className="flex items-center justify-between mb-3">
                            <button
                                onClick={() => selectNode(null)}
                                className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 transition-colors"
                            >
                                <ArrowLeft className="h-4 w-4" />
                                Back to Present
                            </button>
                            <div className="flex items-center gap-2">
                                <span className="text-sm font-semibold text-gray-900">
                                    {selectedNode.years}
                                </span>
                                <span className="text-sm text-gray-500">at</span>
                                <div className="flex items-center gap-1.5">
                                    {selectedNode.clubLogo && (
                                        <img src={selectedNode.clubLogo} alt="" className="w-5 h-5 rounded-full object-cover" />
                                    )}
                                    <span className="text-sm font-medium text-gray-900">
                                        {selectedNode.clubName}
                                    </span>
                                </div>
                                <Badge
                                    className="text-xs text-white"
                                    style={{ backgroundColor: LEVEL_COLORS[selectedNode.primaryLevel] || '#6b7280' }}
                                >
                                    {selectedNode.primaryLevel}
                                </Badge>
                            </div>
                        </div>

                        {/* Stats summary */}
                        <div className="grid grid-cols-3 gap-4 mb-3">
                            <div className="text-center p-2 bg-white rounded-lg">
                                <div className="text-xl font-bold text-gray-900">{selectedNode.stats.apps}</div>
                                <div className="text-xs text-gray-500">Apps</div>
                            </div>
                            <div className="text-center p-2 bg-white rounded-lg">
                                <div className="text-xl font-bold text-blue-600">{selectedNode.stats.goals}</div>
                                <div className="text-xs text-gray-500">Goals</div>
                            </div>
                            <div className="text-center p-2 bg-white rounded-lg">
                                <div className="text-xl font-bold text-green-600">{selectedNode.stats.assists}</div>
                                <div className="text-xs text-gray-500">Assists</div>
                            </div>
                        </div>

                        {/* Competition breakdown */}
                        {selectedNode.competitions?.length > 0 && (
                            <div>
                                <h4 className="text-xs font-medium text-gray-500 mb-1.5">Competitions</h4>
                                <div className="space-y-1">
                                    {selectedNode.competitions.map((comp, idx) => (
                                        <div
                                            key={idx}
                                            className="flex items-center justify-between text-sm bg-white rounded px-3 py-1.5"
                                        >
                                            <span className="font-medium text-gray-700">{comp.league}</span>
                                            <span className="text-gray-500">
                                                {comp.apps} apps, {comp.goals}G {comp.assists}A
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    )
}

export default SeasonStatsPanel
