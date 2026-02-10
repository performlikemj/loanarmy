import { useState } from 'react'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { MessageCircle, LogIn } from 'lucide-react'
import { GolChatWindow } from './GolChatWindow'
import { useGolChat } from '@/hooks/useGolChat'
import { useAuth, useAuthUI } from '@/context/AuthContext'

export function GolPanel() {
  const [open, setOpen] = useState(false)
  const chat = useGolChat()
  const { token } = useAuth()
  const { openLoginModal } = useAuthUI()

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
          {token ? (
            <GolChatWindow {...chat} />
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 px-6 py-12 text-center">
              <MessageCircle className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">Sign in to chat</h3>
              <p className="text-sm text-muted-foreground mb-6">
                Log in to chat with the GOL Assistant and search for data about academy players, loan spells, and career journeys.
              </p>
              <Button onClick={() => { setOpen(false); openLoginModal() }}>
                <LogIn className="h-4 w-4 mr-2" />
                Sign in
              </Button>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  )
}
