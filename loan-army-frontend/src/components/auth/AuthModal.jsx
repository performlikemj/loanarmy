import { useState, useEffect } from 'react'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from '@/components/ui/dialog'
import { Loader2, LogOut, AlertCircle, CheckCircle } from 'lucide-react'

export function AuthModal() {
    const { isLoginModalOpen, closeLoginModal, logout } = useAuthUI()
    const auth = useAuth()
    const [email, setEmail] = useState('')
    const [code, setCode] = useState('')
    const [requestSent, setRequestSent] = useState(false)
    const [busy, setBusy] = useState(false)
    const [status, setStatus] = useState(null)
    const [displayNameInput, setDisplayNameInput] = useState(auth.displayName || '')
    const [displayNameBusy, setDisplayNameBusy] = useState(false)
    const [displayNameStatus, setDisplayNameStatus] = useState(null)

    useEffect(() => {
        if (!isLoginModalOpen) {
            setEmail('')
            setCode('')
            setRequestSent(false)
            setStatus(null)
            setDisplayNameStatus(null)
        }
    }, [isLoginModalOpen])

    useEffect(() => {
        setDisplayNameInput(auth.displayName || '')
    }, [auth.displayName, auth.token])

    const handleRequest = async (event) => {
        event.preventDefault()
        const trimmed = (email || '').trim().toLowerCase()
        if (!trimmed) {
            setStatus({ type: 'error', message: 'Enter the email you use for The Academy Watch.' })
            return
        }
        setBusy(true)
        try {
            await APIService.requestLoginCode(trimmed)
            setStatus({ type: 'success', message: 'Code sent! Check your email within five minutes.' })
            setRequestSent(true)
        } catch (error) {
            setStatus({ type: 'error', message: error?.body?.error || error.message || 'Failed to send login code.' })
        } finally {
            setBusy(false)
        }
    }

    const handleVerify = async (event) => {
        event.preventDefault()
        const trimmedEmail = (email || '').trim().toLowerCase()
        const trimmedCode = (code || '').trim()
        if (!trimmedEmail || !trimmedCode) {
            setStatus({ type: 'error', message: 'Enter both email and code to continue.' })
            return
        }
        setBusy(true)
        try {
            const result = await APIService.verifyLoginCode(trimmedEmail, trimmedCode)
            const confirmed = !!result?.display_name_confirmed
            setStatus({ type: 'success', message: confirmed ? 'Signed in! Welcome back.' : 'Signed in! Pick a display name to finish.' })
            setRequestSent(false)
            setCode('')
            if (!confirmed) {
                setDisplayNameInput(result?.display_name || auth.displayName || '')
                setDisplayNameStatus(null)
            } else {
                setTimeout(() => {
                    closeLoginModal()
                }, 700)
            }
        } catch (error) {
            setStatus({ type: 'error', message: error?.body?.error || error.message || 'Verification failed. Try again.' })
        } finally {
            setBusy(false)
        }
    }

    const handleDisplayNameSave = async (event) => {
        event.preventDefault()
        const trimmed = (displayNameInput || '').trim()
        if (trimmed.length < 3) {
            setDisplayNameStatus({ type: 'error', message: 'Display name must be at least 3 characters.' })
            return
        }
        setDisplayNameBusy(true)
        try {
            await APIService.updateDisplayName(trimmed)
            await APIService.refreshProfile().catch(() => { })
            setDisplayNameStatus({ type: 'success', message: 'Display name updated.' })
        } catch (error) {
            setDisplayNameStatus({ type: 'error', message: error?.body?.error || error.message || 'Failed to update display name.' })
        } finally {
            setDisplayNameBusy(false)
        }
    }

    return (
        <Dialog open={isLoginModalOpen} onOpenChange={(open) => { if (!open) closeLoginModal() }}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>{auth.token ? 'Account' : 'Sign in to The Academy Watch'}</DialogTitle>
                    <DialogDescription>
                        {auth.token
                            ? 'Update your display name or sign out of your session.'
                            : 'We’ll email you a one-time code to finish signing in.'}
                    </DialogDescription>
                </DialogHeader>

                {auth.token ? (
                    <div className="space-y-4">
                        <div className="rounded-md border bg-muted/40 p-3 text-sm">
                            <div className="font-medium text-gray-900">Signed in as {auth.displayName || 'GOL supporter'}</div>
                            {auth.isAdmin && (
                                <div className="text-xs text-gray-600 mt-1">
                                    Admin access: {auth.hasApiKey ? 'ready' : 'missing API key'}
                                </div>
                            )}
                        </div>
                        <form className="space-y-2" onSubmit={handleDisplayNameSave}>
                            <Label htmlFor="display-name">Display name</Label>
                            <Input
                                id="display-name"
                                value={displayNameInput}
                                onChange={(e) => setDisplayNameInput(e.target.value)}
                                maxLength={40}
                                placeholder="Your public name"
                            />
                            {displayNameStatus && (
                                <p className={`text-xs ${displayNameStatus.type === 'error' ? 'text-red-600' : 'text-emerald-600'}`}>
                                    {displayNameStatus.message}
                                </p>
                            )}
                            <div className="flex items-center gap-2">
                                <Button size="sm" type="submit" disabled={displayNameBusy}>
                                    {displayNameBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save
                                </Button>
                                <Button size="sm" variant="ghost" type="button" onClick={() => setDisplayNameInput(auth.displayName || '')}>
                                    Reset
                                </Button>
                            </div>
                        </form>
                    </div>
                ) : (
                    <div className="space-y-4">
                        <form className="space-y-3" onSubmit={handleRequest}>
                            <div className="space-y-2">
                                <Label htmlFor="login-email">Email</Label>
                                <Input
                                    id="login-email"
                                    type="email"
                                    autoComplete="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="you@example.com"
                                    required
                                />
                            </div>
                            <Button type="submit" disabled={busy} className="w-full">
                                {busy && !requestSent ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                Send login code
                            </Button>
                        </form>

                        {requestSent && (
                            <form className="space-y-3" onSubmit={handleVerify}>
                                <div className="space-y-2">
                                    <Label htmlFor="login-code">Verification code</Label>
                                    <Input
                                        id="login-code"
                                        value={code}
                                        onChange={(e) => setCode(e.target.value)}
                                        placeholder="Enter the 11-character code"
                                        autoComplete="one-time-code"
                                    />
                                </div>
                                <Button type="submit" disabled={busy} className="w-full">
                                    {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                    Verify & sign in
                                </Button>
                            </form>
                        )}

                        {status && (
                            <Alert className={`border ${status.type === 'error' ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
                                {status.type === 'error' ? <AlertCircle className="h-4 w-4" /> : <CheckCircle className="h-4 w-4" />}
                                <AlertDescription>{status.message}</AlertDescription>
                            </Alert>
                        )}
                    </div>
                )}

                <DialogFooter className="flex items-center justify-between">
                    {auth.token ? (
                        <Button variant="ghost" onClick={() => { logout(); closeLoginModal() }}>
                            <LogOut className="mr-2 h-4 w-4" /> Log out
                        </Button>
                    ) : requestSent ? (
                        <Button variant="ghost" onClick={() => { setRequestSent(false); setCode(''); setStatus(null) }}>
                            Back
                        </Button>
                    ) : <span />}
                    <Button variant="outline" onClick={closeLoginModal}>Close</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
