import React, { useState, useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ThumbsUp, ThumbsDown, ChevronLeft, ChevronRight, Plus, Send, Loader2, Video, X } from 'lucide-react'
import { APIService } from '@/lib/api'

function extractVideoId(url) {
    if (!url) return null
    const match = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]{11})/)
    return match ? match[1] : null
}

function isValidYoutubeUrl(url) {
    return /^https?:\/\/(www\.)?youtube\.com\/watch\?v=[\w-]{11}/.test(url) ||
           /^https?:\/\/youtu\.be\/[\w-]{11}/.test(url)
}

export function PlayerVideoGallery({ playerApiId }) {
    const [videos, setVideos] = useState([])
    const [loading, setLoading] = useState(true)
    const [currentIndex, setCurrentIndex] = useState(0)
    const [showForm, setShowForm] = useState(false)
    const [submitUrl, setSubmitUrl] = useState('')
    const [submitTitle, setSubmitTitle] = useState('')
    const [submitting, setSubmitting] = useState(false)
    const [urlError, setUrlError] = useState('')

    const isLoggedIn = !!APIService.userToken

    useEffect(() => {
        loadVideos()
    }, [playerApiId])

    const loadVideos = async () => {
        setLoading(true)
        try {
            const data = await APIService.getPlayerVideos(playerApiId)
            setVideos(data?.videos || data || [])
        } catch (err) {
            console.error('Failed to load videos:', err)
            setVideos([])
        } finally {
            setLoading(false)
        }
    }

    const handleSubmit = async (e) => {
        e.preventDefault()
        if (!isValidYoutubeUrl(submitUrl)) {
            setUrlError('Please enter a valid YouTube URL (youtube.com/watch?v=... or youtu.be/...)')
            return
        }
        setSubmitting(true)
        setUrlError('')
        try {
            const created = await APIService.submitPlayerVideo(playerApiId, submitUrl, submitTitle || null)
            if (created) {
                setVideos(prev => [...prev, created])
                setCurrentIndex(videos.length)
            }
            setSubmitUrl('')
            setSubmitTitle('')
            setShowForm(false)
        } catch (err) {
            console.error('Failed to submit video:', err)
            setUrlError(err.message || 'Failed to submit video')
        } finally {
            setSubmitting(false)
        }
    }

    const handleVote = async (videoId, vote) => {
        if (!isLoggedIn) return
        try {
            const result = await APIService.voteOnVideo(videoId, vote)
            setVideos(prev => prev.map(v =>
                v.id === videoId
                    ? { ...v, upvotes: result?.upvotes ?? v.upvotes, downvotes: result?.downvotes ?? v.downvotes, user_vote: vote }
                    : v
            ))
        } catch (err) {
            console.error('Failed to vote:', err)
        }
    }

    const currentVideo = videos[currentIndex]
    const videoId = currentVideo ? extractVideoId(currentVideo.youtube_url) || currentVideo.youtube_video_id : null

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
            </div>
        )
    }

    return (
        <div className="space-y-4">
            {videos.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                    <Video className="h-8 w-8 mx-auto mb-2 text-gray-300" />
                    <p className="text-sm">No videos yet. Be the first to share one!</p>
                </div>
            ) : (
                <>
                    {/* Video Embed */}
                    <div className="aspect-video w-full bg-black rounded-lg overflow-hidden">
                        {videoId ? (
                            <iframe
                                src={`https://www.youtube.com/embed/${videoId}`}
                                title={currentVideo.title || 'Player video'}
                                className="w-full h-full"
                                allowFullScreen
                                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            />
                        ) : (
                            <div className="w-full h-full flex items-center justify-center text-gray-400">
                                Invalid video URL
                            </div>
                        )}
                    </div>

                    {/* Navigation + Info */}
                    <div className="flex items-center justify-between">
                        <Button
                            variant="outline"
                            size="icon"
                            onClick={() => setCurrentIndex(i => Math.max(0, i - 1))}
                            disabled={currentIndex === 0}
                        >
                            <ChevronLeft className="h-4 w-4" />
                        </Button>

                        <div className="text-center flex-1 mx-4 min-w-0">
                            <p className="text-sm font-medium text-gray-900 truncate">
                                {currentVideo.title || 'Untitled Video'}
                            </p>
                            <p className="text-xs text-gray-500">
                                {currentVideo.submitted_by_name && `by ${currentVideo.submitted_by_name} · `}
                                {currentIndex + 1} of {videos.length}
                            </p>
                        </div>

                        <Button
                            variant="outline"
                            size="icon"
                            onClick={() => setCurrentIndex(i => Math.min(videos.length - 1, i + 1))}
                            disabled={currentIndex === videos.length - 1}
                        >
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>

                    {/* Votes */}
                    <div className="flex items-center justify-center gap-4">
                        <button
                            onClick={() => handleVote(currentVideo.id, 1)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-colors ${
                                currentVideo.user_vote === 1
                                    ? 'bg-blue-100 text-blue-700'
                                    : 'bg-gray-100 text-gray-600 hover:bg-blue-50'
                            } ${!isLoggedIn ? 'cursor-default opacity-60' : 'cursor-pointer'}`}
                        >
                            <ThumbsUp className="h-4 w-4" />
                            <span>{currentVideo.upvotes || 0}</span>
                        </button>
                        <button
                            onClick={() => handleVote(currentVideo.id, -1)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-colors ${
                                currentVideo.user_vote === -1
                                    ? 'bg-red-100 text-red-600'
                                    : 'bg-gray-100 text-gray-600 hover:bg-red-50'
                            } ${!isLoggedIn ? 'cursor-default opacity-60' : 'cursor-pointer'}`}
                        >
                            <ThumbsDown className="h-4 w-4" />
                            <span>{currentVideo.downvotes || 0}</span>
                        </button>
                    </div>
                </>
            )}

            {/* Submit Video */}
            {isLoggedIn && !showForm && (
                <div className="text-center">
                    <Button variant="outline" size="sm" onClick={() => setShowForm(true)}>
                        <Plus className="h-4 w-4 mr-1" />
                        Submit a Video
                    </Button>
                </div>
            )}

            {showForm && (
                <Card>
                    <CardContent className="pt-4 space-y-3">
                        <div className="flex items-center justify-between">
                            <h4 className="text-sm font-medium">Submit a YouTube Video</h4>
                            <button onClick={() => { setShowForm(false); setUrlError('') }} className="text-gray-400 hover:text-gray-600">
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                        <form onSubmit={handleSubmit} className="space-y-3">
                            <div>
                                <Input
                                    placeholder="https://www.youtube.com/watch?v=..."
                                    value={submitUrl}
                                    onChange={(e) => { setSubmitUrl(e.target.value); setUrlError('') }}
                                />
                                {urlError && <p className="text-xs text-red-500 mt-1">{urlError}</p>}
                            </div>
                            <Input
                                placeholder="Title (optional)"
                                value={submitTitle}
                                onChange={(e) => setSubmitTitle(e.target.value)}
                                maxLength={200}
                            />
                            <Button type="submit" size="sm" disabled={!submitUrl || submitting} className="w-full">
                                {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Send className="h-4 w-4 mr-1" />}
                                Submit
                            </Button>
                        </form>
                    </CardContent>
                </Card>
            )}

            {!isLoggedIn && (
                <p className="text-center text-xs text-gray-400">Sign in to submit videos and vote</p>
            )}
        </div>
    )
}

export default PlayerVideoGallery
