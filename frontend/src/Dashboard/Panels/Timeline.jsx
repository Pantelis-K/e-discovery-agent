import React from 'react'
import { Box, Typography, useTheme } from '@mui/material'

const ADMIN_BASE = 'http://localhost:8000/admin'

// One shape per event: a square per run/batch start, and one circle-or-diamond
// per document once the LLM has proposed a decision for it (deduped by doc_id —
// "1 shape per document" even if a doc gets re-proposed, e.g. a confidence-floor
// handoff). Sourced from two places: the persisted AgentRun/Decision history
// (fetched once on load, so a refresh doesn't lose anything) plus the live SSE
// events for the run in progress right now (not in the DB snapshot yet).
// Every shape links back to its actual DB record via the Django admin.
function buildShapes({ dbRuns, dbDecisions, liveEvents }) {
    const shapes = []
    const seenRuns = new Set()
    const seenDocs = new Set()

    // dbRuns and dbDecisions come from two separate endpoints — merge and sort
    // by real timestamp before building shapes, otherwise every run square ends
    // up bunched before every decision shape instead of interleaved in the
    // order things actually happened.
    const historical = [
        ...dbRuns.map((run) => ({ kind: 'run', at: run.started_at, run })),
        ...dbDecisions.map((d) => ({ kind: 'decision', at: d.proposed_at, decision: d })),
    ].sort((a, b) => new Date(a.at) - new Date(b.at))

    historical.forEach((item) => {
        if (item.kind === 'run') {
            const run = item.run
            if (seenRuns.has(run.run_id)) return
            seenRuns.add(run.run_id)
            shapes.push({
                key: `run-${run.run_id}`,
                kind: 'square',
                runId: run.run_id,
                title: `Run ${run.run_id} — ${run.topic} (${run.status}) — click to load into Actions Table`,
            })
        } else {
            const d = item.decision
            if (seenDocs.has(d.doc_id)) return
            seenDocs.add(d.doc_id)
            shapes.push({
                key: `doc-${d.doc_id}`,
                docId: d.doc_id,
                title: `${d.doc_id} — relevant=${d.relevance}, privilege=${d.privilege} (${d.proposed_by})`,
                link: `${ADMIN_BASE}/agent/decision/${d.decision_id}/change/`,
            })
        }
    })

    liveEvents.forEach(({ type, data }, i) => {
        if (type === 'run_started' && data.run_id && !seenRuns.has(data.run_id)) {
            seenRuns.add(data.run_id)
            shapes.push({
                key: `run-${data.run_id}`,
                kind: 'square',
                runId: data.run_id,
                title: `Run started — ${data.topic || 'untitled'} (batch size ${data.batch_size ?? '?'}) — click to load into Actions Table`,
            })
        } else if (type === 'document_decision_proposed' && data.doc_id && !seenDocs.has(data.doc_id)) {
            seenDocs.add(data.doc_id)
            shapes.push({
                key: `doc-${data.doc_id}`,
                docId: data.doc_id,
                title: `${data.doc_id} — relevant=${data.relevance}, privilege=${data.privilege} (${data.proposed_by})`,
                link: data.decision_id ? `${ADMIN_BASE}/agent/decision/${data.decision_id}/change/` : null,
            })
        }
    })

    return shapes
}

const SHAPE_SX = {
    square: { borderRadius: 0, transform: 'none' },
    circle: { borderRadius: '50%', transform: 'none' },
    diamond: { borderRadius: 0, transform: 'rotate(45deg)' },
}

// Diamonds render 25% smaller than squares/circles (40.5px vs 54px).
const SHAPE_SIZE = {
    square: 54,
    circle: 54,
    diamond: 40.5,
}

// square = red (batch start), circle = brand accent blue (LLM decision, not yet
// corrected), diamond = yellow (reviewer has corrected this document).
const SHAPE_COLOR = {
    square: '#000000',
    circle: '#3B4CCA',
    diamond: '#F5C518',
}

// A diagonal glossy highlight over the base color plus a drop shadow + inset
// bevel — reads as a raised glass/plastic bead rather than a flat tile.
function shapeDepthSx(kind) {
    return {
        background: `linear-gradient(135deg, rgba(255,255,255,0.65) 0%, rgba(255,255,255,0.05) 40%, rgba(0,0,0,0.15) 100%), ${SHAPE_COLOR[kind]}`,
        boxShadow: '0 4px 8px rgba(0,0,0,0.35), inset 0 -4px 6px rgba(0,0,0,0.3), inset 0 3px 4px rgba(255,255,255,0.5)',
    }
}

export default function Timeline({ events, correctedDocIds, dbRuns, dbDecisions, dbCorrections, onSelectRun, sx }) {
    const theme = useTheme()
    const { muted } = theme.palette.brand
    const border = theme.palette.divider

    // A doc counts as "corrected" whether that came from a persisted Correction
    // row or from an in-progress local edit not yet submitted.
    const correctedSet = new Set(correctedDocIds || [])
    ;(dbCorrections || []).forEach((c) => correctedSet.add(c.doc_id))

    const shapes = buildShapes({
        dbRuns: dbRuns || [],
        dbDecisions: dbDecisions || [],
        liveEvents: events || [],
    })

    return (
        <Box sx={{ border: `1px solid ${border}`, bgcolor: '#fff', p: 2, display: 'flex', flexDirection: 'column', gap: 1, height: '100%', boxSizing: 'border-box', ...sx }}>
            <Typography sx={{ fontWeight: 700, color: muted, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em', flexShrink: 0 }}>
                Timeline
            </Typography>
            <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', overflowX: 'auto', overflowY: 'hidden' }}>
                {shapes.length === 0 ? (
                    <Typography sx={{ fontSize: 12, color: muted }}>Nothing yet — start a review to populate this.</Typography>
                ) : (
                    // width: 'fit-content' (not 100%) so the rail below is sized to the
                    // shapes themselves, not stretched across the whole panel — it ends
                    // exactly at the last data point instead of running past it.
                    <Box sx={{ position: 'relative', display: 'flex', flexWrap: 'nowrap', alignItems: 'center', gap: 1.625, width: 'fit-content' }}>
                        <Box sx={{ position: 'absolute', left: 0, right: 0, top: '50%', height: 2, bgcolor: '#000', transform: 'translateY(-50%)', zIndex: 0 }} />
                        {shapes.map((shape) => {
                            const kind = shape.kind || (correctedSet.has(shape.docId) ? 'diamond' : 'circle')
                            return (
                                <Box
                                    key={shape.key}
                                    title={shape.title}
                                    onClick={() => {
                                        if (kind === 'square' && shape.runId) {
                                            onSelectRun?.(shape.runId)
                                        } else if (shape.link) {
                                            window.open(shape.link, '_blank', 'noopener,noreferrer')
                                        }
                                    }}
                                    sx={{
                                        position: 'relative',
                                        zIndex: 1,
                                        width: SHAPE_SIZE[kind],
                                        height: SHAPE_SIZE[kind],
                                        flexShrink: 0,
                                        cursor: shape.link || shape.runId ? 'pointer' : 'default',
                                        ...shapeDepthSx(kind),
                                        ...SHAPE_SX[kind],
                                    }}
                                />
                            )
                        })}
                    </Box>
                )}
            </Box>
        </Box>
    )
}
