import { useState, useRef, useEffect, useCallback } from 'react'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { ChartRenderer } from './ChartRenderer'
import { DataTableRenderer } from './DataTableRenderer'

export function ChatPanel({ teamId = null, leagueId = null }) {
    const auth = useAuth()
    const { openLoginModal } = useAuthUI()
    const [activeSession, setActiveSession] = useState(null)
    const [messages, setMessages] = useState([])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const messagesEndRef = useRef(null)
    const inputRef = useRef(null)

    const scrollToBottom = useCallback(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [])

    useEffect(() => { scrollToBottom() }, [messages, scrollToBottom])

    const sendMessage = async () => {
        if (!input.trim() || loading) return
        const userMsg = input.trim()
        setInput('')
        setMessages(prev => [...prev, { role: 'user', content: userMsg }])
        setLoading(true)

        try {
            let sessionId = activeSession
            if (!sessionId) {
                const session = await APIService.createChatSession({ team_id: teamId, league_id: leagueId })
                sessionId = session.id
                setActiveSession(sessionId)
            }
            const response = await APIService.sendChatMessage(sessionId, userMsg)
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: response.message,
                metadata: response.metadata,
            }])
        } catch (error) {
            console.error('Chat error:', error)
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: 'Sorry, something went wrong. Please try again.',
            }])
        } finally {
            setLoading(false)
            inputRef.current?.focus()
        }
    }

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            sendMessage()
        }
    }

    const startNewSession = () => {
        setActiveSession(null)
        setMessages([])
    }

    if (!auth.token) {
        return (
            <div className="border border-dashed border-gray-300 rounded-lg p-8 text-center text-gray-500">
                <svg className="h-8 w-8 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <p className="mb-3">Sign in to chat with the Academy Watch analyst</p>
                <button
                    onClick={openLoginModal}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm"
                >
                    Sign In
                </button>
            </div>
        )
    }

    const suggestions = [
        "Who are the top scoring loanees?",
        "Compare loan performance by league",
        "Show me minutes played distribution",
        "Which loanees have the most assists?",
    ]

    return (
        <div className="flex flex-col h-[600px] border rounded-lg bg-white shadow-sm">
            {/* Header */}
            <div className="px-4 py-3 border-b flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <svg className="h-5 w-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                    <h3 className="font-semibold text-gray-900">Academy Watch Analyst</h3>
                </div>
                {activeSession && (
                    <button
                        onClick={startNewSession}
                        className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100"
                    >
                        New Chat
                    </button>
                )}
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.length === 0 && (
                    <div className="text-center text-gray-500 py-8">
                        <p className="text-sm mb-4">Ask me anything about academy players, stats, or transfers.</p>
                        <div className="flex flex-wrap gap-2 justify-center">
                            {suggestions.map(q => (
                                <button
                                    key={q}
                                    onClick={() => setInput(q)}
                                    className="text-xs px-3 py-1.5 border rounded-full hover:bg-gray-50 text-gray-600"
                                >
                                    {q}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {messages.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] rounded-lg px-4 py-2 ${msg.role === 'user'
                            ? 'bg-blue-600 text-white'
                            : 'bg-gray-100 text-gray-900'
                            }`}>
                            <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                            {msg.metadata?.charts?.map((chart, ci) => (
                                <ChartRenderer key={ci} base64Data={chart} />
                            ))}
                            {msg.metadata?.tables?.map((table, ti) => (
                                <DataTableRenderer key={ti} data={table} />
                            ))}
                            {msg.metadata?.tool_calls?.length > 0 && (
                                <div className="mt-1 text-xs opacity-60">
                                    Used: {msg.metadata.tool_calls.map(tc => tc.tool).join(', ')}
                                </div>
                            )}
                        </div>
                    </div>
                ))}

                {loading && (
                    <div className="flex justify-start">
                        <div className="bg-gray-100 rounded-lg px-4 py-2">
                            <div className="flex items-center gap-2 text-sm text-gray-500">
                                <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                </svg>
                                Analyzing...
                            </div>
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-4 border-t">
                <form onSubmit={(e) => { e.preventDefault(); sendMessage() }} className="flex gap-2">
                    <input
                        ref={inputRef}
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Ask about players, stats, comparisons..."
                        disabled={loading}
                        className="flex-1 px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                        maxLength={4000}
                    />
                    <button
                        type="submit"
                        disabled={loading || !input.trim()}
                        className="px-3 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                        </svg>
                    </button>
                </form>
            </div>
        </div>
    )
}
