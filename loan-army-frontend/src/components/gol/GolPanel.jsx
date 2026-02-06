import { useState } from 'react'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { MessageCircle } from 'lucide-react'
import { GolChatWindow } from './GolChatWindow'
import { useGolChat } from '@/hooks/useGolChat'

export function GolPanel() {
  const [open, setOpen] = useState(false)
  const chat = useGolChat()

  return (
    <>
      {/* Floating trigger button */}
      <Button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full shadow-lg bg-blue-600 hover:bg-blue-700"
        size="icon"
      >
        <MessageCircle className="h-6 w-6 text-white" />
      </Button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-full sm:w-[440px] p-0 flex flex-col">
          <SheetHeader className="px-4 py-3 border-b">
            <SheetTitle className="text-lg font-semibold">GOL Assistant</SheetTitle>
          </SheetHeader>
          <GolChatWindow {...chat} />
        </SheetContent>
      </Sheet>
    </>
  )
}
