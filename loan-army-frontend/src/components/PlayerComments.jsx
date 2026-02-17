import React, { useState, useEffect, useCallback } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { ThumbsUp, ThumbsDown, Trash2, MessageCircle, Send, Loader2, ChevronDown, Eye } from 'lucide-react'
import { APIService } from '@/lib/api'
import { formatDistanceToNow } from 'date-fns'

export function PlayerComments({ playerApiId }) {
    const [comments, setComments] = useState([])
    const [loading, setLoading] = useState(true)
    const [loadingMore, setLoadingMore] = useState(false)
    const [hasMore, setHasMore] = useState(false)
    const [offset, setOffset] = useState(0)
    const [newComment, setNewComment] = useState('')
    const [submitting, setSubmitting] = useState(false)
    const [sort, setSort] = useState('newest')
    const [expandedHidden, setExpandedHidden] = useState({})
    const [error, setError] = useState(null)

    const LIMIT = 20
    const isLoggedIn = !!APIService.userToken
    const currentDisplayName = APIService.displayName

    const fetchComments = useCallback(async (reset = false) => {
        const currentOffset = reset ? 0 : offset
        if (reset) setLoading(true)
        else setLoadingMore(true)

        try {
            const data = await APIService.getPlayerComments(playerApiId, { sort, limit: LIMIT, offset: currentOffset })
            const fetched = data?.comments || data || []
            if (reset) {
                setComments(fetched)
                setOffset(fetched.length)
            } else {
                setComments(prev => [...prev, ...fetched])
                setOffset(currentOffset + fetched.length)
            }
            setHasMore(fetched.length >= LIMIT)
            setError(null)
        } catch (err) {
            console.error('Failed to load comments:', err)
            setError('Failed to load comments')
            if (reset) setComments([])
        } finally {
            setLoading(false)
            setLoadingMore(false)
        }
    }, [playerApiId, sort, offset])

    useEffect(() => {
        fetchComments(true)
    }, [playerApiId, sort])

    const handleSubmit = async (e) => {
        e.preventDefault()
        if (!newComment.trim() || submitting) return
        setSubmitting(true)
        try {
            const created = await APIService.postPlayerComment(playerApiId, newComment.trim())
            if (created) {
                setComments(prev => [created, ...prev])
            }
            setNewComment('')
        } catch (err) {
            console.error('Failed to post comment:', err)
        } finally {
            setSubmitting(false)
        }
    }

    const handleVote = async (commentId, vote) => {
        try {
            const result = await APIService.voteOnComment(commentId, vote)
            setComments(prev => prev.map(c =>
                c.id === commentId
                    ? { ...c, upvotes: result?.upvotes ?? c.upvotes, downvotes: result?.downvotes ?? c.downvotes, user_vote: vote }
                    : c
            ))
        } catch (err) {
            console.error('Failed to vote:', err)
        }
    }

    const handleDelete = async (commentId) => {
        try {
            await APIService.deleteComment(commentId)
            setComments(prev => prev.filter(c => c.id !== commentId))
        } catch (err) {
            console.error('Failed to delete comment:', err)
        }
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
            </div>
        )
    }

    return (
        <div className="space-y-4">
            {/* Add Comment Form */}
            {isLoggedIn ? (
                <form onSubmit={handleSubmit} className="space-y-3">
                    <Textarea
                        placeholder="Share your thoughts on this player..."
                        value={newComment}
                        onChange={(e) => setNewComment(e.target.value)}
                        className="min-h-[80px] resize-none"
                        maxLength={2000}
                    />
                    <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">{newComment.length}/2000</span>
                        <Button type="submit" size="sm" disabled={!newComment.trim() || submitting}>
                            {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Send className="h-4 w-4 mr-1" />}
                            Post Comment
                        </Button>
                    </div>
                </form>
            ) : (
                <Card className="bg-gray-50">
                    <CardContent className="py-4 text-center text-sm text-gray-500">
                        <MessageCircle className="h-5 w-5 mx-auto mb-2 text-gray-400" />
                        Sign in to leave a comment
                    </CardContent>
                </Card>
            )}

            {/* Sort */}
            {comments.length > 0 && (
                <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">Sort:</span>
                    {['newest', 'oldest', 'top'].map(s => (
                        <button
                            key={s}
                            onClick={() => setSort(s)}
                            className={`text-xs px-2 py-1 rounded-full transition-colors ${sort === s ? 'bg-blue-100 text-blue-700 font-medium' : 'text-gray-500 hover:bg-gray-100'}`}
                        >
                            {s.charAt(0).toUpperCase() + s.slice(1)}
                        </button>
                    ))}
                </div>
            )}

            {/* Comments List */}
            {error && <p className="text-sm text-red-500 text-center py-4">{error}</p>}

            {comments.length === 0 && !error ? (
                <div className="text-center py-8 text-gray-500">
                    <MessageCircle className="h-8 w-8 mx-auto mb-2 text-gray-300" />
                    <p className="text-sm">No comments yet. Be the first!</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {comments.map((comment) => (
                        <div key={comment.id} className="flex gap-3 p-3 rounded-lg hover:bg-gray-50 transition-colors">
                            <Avatar className="h-8 w-8 flex-shrink-0">
                                <AvatarFallback className="text-xs bg-blue-100 text-blue-700">
                                    {(comment.author_name || 'U').charAt(0).toUpperCase()}
                                </AvatarFallback>
                            </Avatar>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="text-sm font-medium text-gray-900">{comment.author_name || 'Anonymous'}</span>
                                    <span className="text-xs text-gray-400">
                                        {comment.created_at && formatDistanceToNow(new Date(comment.created_at), { addSuffix: true })}
                                    </span>
                                </div>

                                {comment.is_hidden && !expandedHidden[comment.id] ? (
                                    <div className="flex items-center gap-2">
                                        <p className="text-sm text-gray-400 italic">[Comment hidden due to community reports]</p>
                                        <button
                                            onClick={() => setExpandedHidden(prev => ({ ...prev, [comment.id]: true }))}
                                            className="text-xs text-blue-500 hover:underline flex items-center gap-1"
                                        >
                                            <Eye className="h-3 w-3" /> Show
                                        </button>
                                    </div>
                                ) : (
                                    <p className="text-sm text-gray-700 whitespace-pre-wrap break-words">{comment.content}</p>
                                )}

                                {/* Actions */}
                                <div className="flex items-center gap-3 mt-2">
                                    <button
                                        onClick={() => isLoggedIn && handleVote(comment.id, 1)}
                                        className={`flex items-center gap-1 text-xs transition-colors ${comment.user_vote === 1 ? 'text-blue-600' : 'text-gray-400 hover:text-blue-500'} ${!isLoggedIn ? 'cursor-default' : 'cursor-pointer'}`}
                                    >
                                        <ThumbsUp className="h-3.5 w-3.5" />
                                        <span>{comment.upvotes || 0}</span>
                                    </button>
                                    <button
                                        onClick={() => isLoggedIn && handleVote(comment.id, -1)}
                                        className={`flex items-center gap-1 text-xs transition-colors ${comment.user_vote === -1 ? 'text-red-500' : 'text-gray-400 hover:text-red-400'} ${!isLoggedIn ? 'cursor-default' : 'cursor-pointer'}`}
                                    >
                                        <ThumbsDown className="h-3.5 w-3.5" />
                                        <span>{comment.downvotes || 0}</span>
                                    </button>
                                    {currentDisplayName && comment.author_name === currentDisplayName && (
                                        <button
                                            onClick={() => handleDelete(comment.id)}
                                            className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 transition-colors ml-auto"
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </button>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Load More */}
            {hasMore && (
                <div className="text-center pt-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => fetchComments(false)}
                        disabled={loadingMore}
                    >
                        {loadingMore ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <ChevronDown className="h-4 w-4 mr-1" />}
                        Load More
                    </Button>
                </div>
            )}
        </div>
    )
}

export default PlayerComments
