/**
 * Converts plain text content to formatted HTML.
 * Handles line breaks, bullet points, and basic text structure.
 */

// Common bullet point characters
const BULLET_CHARS = ['•', '·', '-', '*', '–', '—']

// Check if a line looks like a bullet point
function isBulletLine(line) {
  const trimmed = line.trim()
  if (!trimmed) return false
  
  // Check for bullet characters at start
  for (const char of BULLET_CHARS) {
    if (trimmed.startsWith(char + ' ') || trimmed.startsWith(char + '\t')) {
      return true
    }
  }
  
  // Check for numbered lists (1. 2. etc)
  if (/^\d+[\.\)]\s/.test(trimmed)) {
    return true
  }
  
  return false
}

// Extract bullet content without the bullet marker
function extractBulletContent(line) {
  const trimmed = line.trim()
  
  // Remove bullet character
  for (const char of BULLET_CHARS) {
    if (trimmed.startsWith(char + ' ') || trimmed.startsWith(char + '\t')) {
      return trimmed.slice(char.length).trim()
    }
  }
  
  // Handle numbered lists
  const numberedMatch = trimmed.match(/^\d+[\.\)]\s*(.*)/)
  if (numberedMatch) {
    return numberedMatch[1]
  }
  
  return trimmed
}

// Escape HTML characters to prevent XSS
function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }
  return text.replace(/[&<>"']/g, char => map[char])
}

/**
 * Main formatting function - converts plain text to HTML
 * @param {string} text - Plain text input
 * @returns {string} - HTML formatted output
 */
export function formatTextToHtml(text) {
  if (!text || typeof text !== 'string') return ''
  
  // If the text already looks like HTML, return as-is
  if (text.includes('<p>') || text.includes('<br') || text.includes('<ul>') || text.includes('<div>')) {
    return text
  }
  
  // Normalize line endings
  const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  
  // Split by double newlines (paragraph breaks) or single newlines
  const lines = normalized.split('\n')
  
  const result = []
  let currentParagraph = []
  let inList = false
  let listItems = []
  
  const flushParagraph = () => {
    if (currentParagraph.length > 0) {
      const content = currentParagraph
        .map(line => escapeHtml(line))
        .join('<br />')
      if (content.trim()) {
        result.push(`<p>${content}</p>`)
      }
      currentParagraph = []
    }
  }
  
  const flushList = () => {
    if (listItems.length > 0) {
      const items = listItems
        .map(item => `<li>${escapeHtml(item)}</li>`)
        .join('')
      result.push(`<ul>${items}</ul>`)
      listItems = []
      inList = false
    }
  }
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmedLine = line.trim()
    
    // Empty line - flush current content
    if (!trimmedLine) {
      if (inList) {
        flushList()
      } else {
        flushParagraph()
      }
      continue
    }
    
    // Check if this is a bullet point
    if (isBulletLine(line)) {
      // Flush any pending paragraph
      if (!inList) {
        flushParagraph()
      }
      inList = true
      listItems.push(extractBulletContent(line))
    } else {
      // Not a bullet - flush any pending list
      if (inList) {
        flushList()
      }
      currentParagraph.push(trimmedLine)
    }
  }
  
  // Flush any remaining content
  if (inList) {
    flushList()
  }
  flushParagraph()
  
  return result.join('')
}

/**
 * Lightweight version that just handles line breaks
 * Use when you don't need full paragraph/list parsing
 */
export function simpleLineBreaks(text) {
  if (!text || typeof text !== 'string') return ''
  
  // If already has HTML, return as-is
  if (text.includes('<br') || text.includes('<p>')) {
    return text
  }
  
  return escapeHtml(text)
    .replace(/\n\n+/g, '</p><p>')
    .replace(/\n/g, '<br />')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>')
    .replace(/<p><\/p>/g, '')
}

export default formatTextToHtml


