import { useState } from 'react'

export function ChartRenderer({ base64Data }) {
    const [expanded, setExpanded] = useState(false)

    if (!base64Data) return null

    const src = `data:image/png;base64,${base64Data}`

    return (
        <div className="mt-2">
            <img
                src={src}
                alt="Analytics chart"
                className={`rounded cursor-pointer transition-all ${expanded ? 'max-w-full' : 'max-w-[400px]'}`}
                onClick={() => setExpanded(!expanded)}
            />
            <p className="text-xs text-gray-400 mt-1">
                {expanded ? 'Click to shrink' : 'Click to expand'}
            </p>
        </div>
    )
}
