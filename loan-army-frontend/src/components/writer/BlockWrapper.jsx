import React, { useState } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { CommentaryEditor } from '../CommentaryEditor'
import { ChartPreview } from './ChartPreview'
import {
  GripVertical,
  Trash2,
  Lock,
  Unlock,
  Settings,
  Type,
  BarChart3,
  Minus,
  Eye,
  EyeOff,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const BLOCK_TYPE_ICONS = {
  text: Type,
  chart: BarChart3,
  divider: Minus,
}

const BLOCK_TYPE_LABELS = {
  text: 'Text',
  chart: 'Chart',
  divider: 'Divider',
}

export function BlockWrapper({
  block,
  onRemove,
  onTogglePremium,
  onUpdate,
  onEditChart,
  playerId,
  weekRange,
}) {
  const [isCollapsed, setIsCollapsed] = useState(false)

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: block.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  const Icon = BLOCK_TYPE_ICONS[block.type] || Type

  const renderBlockContent = () => {
    if (isCollapsed) {
      return (
        <div className="text-sm text-gray-500 italic">
          {block.type === 'text' && (block.content?.replace(/<[^>]*>/g, '').slice(0, 100) || 'Empty text block')}
          {block.type === 'chart' && `${block.chart_type?.replace('_', ' ')} chart`}
          {block.type === 'divider' && 'Section divider'}
          {block.content?.length > 100 && '...'}
        </div>
      )
    }

    switch (block.type) {
      case 'text':
        return (
          <CommentaryEditor
            value={block.content || ''}
            onChange={(content) => onUpdate({ content })}
            placeholder="Write your content here..."
          />
        )

      case 'chart':
        return (
          <div className="space-y-3">
            <ChartPreview
              block={block}
              playerId={playerId}
              weekRange={weekRange}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onEditChart}
              className="w-full"
            >
              <Settings className="h-4 w-4 mr-2" /> Configure Chart
            </Button>
          </div>
        )

      case 'divider':
        return (
          <div className="py-4">
            <hr className="border-t-2 border-gray-200" />
          </div>
        )

      default:
        return <div className="text-gray-500">Unknown block type</div>
    }
  }

  return (
    <Card
      ref={setNodeRef}
      style={style}
      className={cn(
        'relative transition-all',
        isDragging && 'opacity-50 shadow-lg z-50',
        block.is_premium && 'border-l-4 border-l-amber-500 bg-amber-50/30'
      )}
    >
      {/* Block header with controls */}
      <CardHeader className="py-2 px-3 flex flex-row items-center justify-between space-y-0 bg-gray-50/80 border-b">
        <div className="flex items-center gap-2">
          {/* Drag handle */}
          <button
            {...attributes}
            {...listeners}
            className="cursor-grab active:cursor-grabbing p-1 hover:bg-gray-200 rounded touch-none"
          >
            <GripVertical className="h-4 w-4 text-gray-400" />
          </button>

          {/* Block type badge */}
          <Badge variant="secondary" className="text-xs gap-1">
            <Icon className="h-3 w-3" />
            {BLOCK_TYPE_LABELS[block.type]}
          </Badge>

          {/* Premium indicator */}
          {block.is_premium && (
            <Badge variant="outline" className="text-xs text-amber-700 border-amber-300 bg-amber-50">
              <Lock className="h-3 w-3 mr-1" />
              Premium
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-1">
          {/* Collapse toggle */}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => setIsCollapsed(!isCollapsed)}
            title={isCollapsed ? 'Expand' : 'Collapse'}
          >
            {isCollapsed ? (
              <Eye className="h-4 w-4 text-gray-500" />
            ) : (
              <EyeOff className="h-4 w-4 text-gray-500" />
            )}
          </Button>

          {/* Premium toggle */}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={cn(
              'h-7 w-7 p-0',
              block.is_premium ? 'text-amber-600' : 'text-gray-500'
            )}
            onClick={onTogglePremium}
            title={block.is_premium ? 'Make public' : 'Make premium'}
          >
            {block.is_premium ? (
              <Lock className="h-4 w-4" />
            ) : (
              <Unlock className="h-4 w-4" />
            )}
          </Button>

          {/* Chart settings (only for chart blocks) */}
          {block.type === 'chart' && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={onEditChart}
              title="Configure chart"
            >
              <Settings className="h-4 w-4 text-gray-500" />
            </Button>
          )}

          {/* Delete button */}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-red-500 hover:text-red-700 hover:bg-red-50"
            onClick={onRemove}
            title="Delete block"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>

      {/* Block content */}
      <CardContent className={cn('pt-3', block.type === 'divider' && 'py-1')}>
        {renderBlockContent()}
      </CardContent>
    </Card>
  )
}

export default BlockWrapper

