import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { GolDataCard } from './GolDataCard'
import { Loader2 } from 'lucide-react'

export function GolMessage({ message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className={isUser ? 'bg-blue-600 text-white' : 'bg-green-600 text-white'}>
          {isUser ? 'U' : 'G'}
        </AvatarFallback>
      </Avatar>

      <div className={`flex-1 max-w-[85%] ${isUser ? 'text-right' : ''}`}>
        <div className={`inline-block rounded-lg px-3 py-2 text-sm ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-muted text-foreground'
        }`}>
          {message.content || (message.toolCall && (
            <span className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Looking up {message.toolCall}...
            </span>
          ))}
        </div>

        {/* Data cards */}
        {message.dataCards?.length > 0 && (
          <div className="mt-2 space-y-2">
            {message.dataCards.map((card, i) => (
              <GolDataCard key={i} card={card} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
