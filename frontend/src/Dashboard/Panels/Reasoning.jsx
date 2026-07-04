import React, { useEffect, useRef, useState } from 'react'
import { Box, Typography, useTheme } from '@mui/material'

// Folds the flat SSE event list into one log line per iteration: a step_started
// and its later step_completed merge into a single "tool(args) -> result" line,
// matching the spec's "what tool it called, with what arguments, and (once the
// result comes back) a one-line summary of the result" (§4).
function foldEvents(events) {
    const lines = []
    const stepLineIndex = new Map() // step_id -> index into lines

    events.forEach(({ type, data }, i) => {
        switch (type) {
            case 'run_started':
                lines.push({ key: `run-started-${i}`, text: `Run started — topic: ${data.topic}, batch size: ${data.batch_size}` })
                break
            case 'step_started': {
                const line = { key: `step-${data.step_id}`, text: `→ ${data.tool}(${JSON.stringify(data.arguments)})` }
                stepLineIndex.set(data.step_id, lines.length)
                lines.push(line)
                break
            }
            case 'step_completed': {
                const idx = stepLineIndex.get(data.step_id)
                const resultText = `  result: ${data.result_summary}`
                if (idx !== undefined) {
                    lines[idx] = { ...lines[idx], text: `${lines[idx].text}\n${resultText}` }
                } else {
                    lines.push({ key: `step-completed-${i}`, text: resultText })
                }
                break
            }
            case 'document_decision_proposed':
                lines.push({
                    key: `decision-${data.decision_id ?? i}`,
                    text: `Proposed decision — doc ${data.doc_id}: relevant=${data.relevance}, privilege=${data.privilege}, confidence=${data.confidence} (${data.proposed_by})`,
                })
                break
            case 'human_review_requested':
                lines.push({ key: `handoff-${i}`, text: `Human review requested — doc ${data.doc_id}: ${data.reason}` })
                break
            case 'correction_applied':
                lines.push({ key: `correction-${data.correction_id ?? i}`, text: `Correction applied: ${data.summary}` })
                break
            case 'batch_complete':
                lines.push({ key: 'batch-complete', text: `Batch complete — ${data.proposed} proposed (${data.reason})` })
                break
            case 'run_error':
                lines.push({ key: `error-${i}`, text: `Error (${data.error_type}): ${data.message}` })
                break
            case 'run_paused':
                lines.push({ key: 'run-paused', text: `Run paused: ${data.reason}` })
                break
            default:
                break
        }
    })

    return lines
}

export default function Reasoning({ events, sx }) {
    const theme = useTheme()
    const { muted, accent } = theme.palette.brand
    const border = theme.palette.divider
    const [autoScroll, setAutoScroll] = useState(true)
    const scrollRef = useRef(null)

    const lines = foldEvents(events || [])

    useEffect(() => {
        if (autoScroll && scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
    }, [lines, autoScroll])

    return (
        <Box sx={{ border: `1px solid ${border}`, bgcolor: '#fff', p: 2, display: 'flex', flexDirection: 'column', ...sx }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5, flexShrink: 0 }}>
                <Typography sx={{ fontWeight: 700, color: muted, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Agent Reasoning
                </Typography>
                <Typography
                    onClick={() => setAutoScroll((v) => !v)}
                    sx={{ fontSize: 11, color: autoScroll ? muted : accent, cursor: 'pointer', userSelect: 'none' }}
                >
                    {autoScroll ? 'Pause auto-scroll' : 'Resume auto-scroll'}
                </Typography>
            </Box>
            <Box ref={scrollRef} sx={{ flex: 1, overflow: 'auto' }}>
                {lines.length === 0 ? (
                    <Typography sx={{ fontFamily: 'monospace', fontSize: 13, color: muted }}>
                        No active run — click Bulk approve to start one.
                    </Typography>
                ) : (
                    lines.map((line) => (
                        <Typography
                            key={line.key}
                            sx={{
                                fontFamily: 'monospace',
                                fontSize: 13,
                                whiteSpace: 'pre-wrap',
                                lineHeight: 1.5,
                            }}
                        >
                            {line.text}
                        </Typography>
                    ))
                )}
            </Box>
        </Box>
    )
}
