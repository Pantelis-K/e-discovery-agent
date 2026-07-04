import React, { useEffect, useRef, useState } from 'react'
import { Container, Grid, Paper, Typography, Box, useTheme, Stack } from '@mui/material'
import ActionsTable from './Panels/ActionsTable'
import ActiveDocument from './Panels/ActiveDocument'
import Reasoning from './Panels/Reasoning'
import Timeline from './Panels/Timeline'

const API_BASE = 'http://localhost:8000/api'

// Mirrors the event types agent.loop.run_batch yields (spec §4).
const RUN_EVENT_TYPES = [
    'run_started', 'step_started', 'step_completed', 'document_decision_proposed',
    'human_review_requested', 'correction_applied', 'batch_complete', 'run_error', 'run_paused',
]

// Event types that mean the batch is done and the stream can be closed.
const TERMINAL_EVENT_TYPES = new Set(['batch_complete', 'run_error', 'run_paused'])

export default function Dashboard({ cases }) {
    const [selectedCase, setSelectedCase] = useState(null)
    const [documents, setDocuments] = useState([])
    const [activeDocument, setActiveDocument] = useState(null)
    const [runEvents, setRunEvents] = useState([]) // resets per run — feeds the live Reasoning stream
    const [timelineEvents, setTimelineEvents] = useState([]) // never reset — feeds the audit Timeline
    const [decisions, setDecisions] = useState({}) // doc_id -> document_decision_proposed data
    const [correctedDocIds, setCorrectedDocIds] = useState(new Set()) // docs a reviewer has edited
    const [dbRuns, setDbRuns] = useState([])
    const [dbDecisions, setDbDecisions] = useState([])
    const [dbCorrections, setDbCorrections] = useState([])
    const eventSourceRef = useRef(null)
    const theme = useTheme()
    const { palette } = theme
    const { accent, highlight } = palette.brand

    // Resolves a doc_id the loop just started reading into the full document,
    // then adds it to the table (dedup by doc_id — a doc may be re-read).
    const fetchAndAddDocument = (docId) => {
        fetch(`${API_BASE}/documents/${docId}/`)
            .then((res) => {
                if (!res.ok) throw new Error(`Failed to fetch document ${docId}: ${res.status}`)
                return res.json()
            })
            .then((doc) => {
                setDocuments((prev) => (prev.some((d) => d.doc_id === doc.doc_id) ? prev : [...prev, doc]))
                setActiveDocument((prev) => prev ?? doc)
            })
            .catch((err) => console.error('Failed to fetch streamed document:', err))
    }

    const startRunStream = (runId) => {
        eventSourceRef.current?.close()
        setRunEvents([])
        setDocuments([])
        setActiveDocument(null)
        setDecisions({})

        const source = new EventSource(`${API_BASE}/runs/${runId}/stream/`)
        eventSourceRef.current = source

        RUN_EVENT_TYPES.forEach((type) => {
            source.addEventListener(type, (e) => {
                const data = e.data ? JSON.parse(e.data) : {}
                setRunEvents((prev) => [...prev, { type, data }])
                setTimelineEvents((prev) => [...prev, { type, data }])
                if (type === 'step_started' && data.tool === 'read_document' && data.arguments?.doc_id) {
                    fetchAndAddDocument(data.arguments.doc_id)
                }
                if (type === 'document_decision_proposed' && data.doc_id) {
                    setDecisions((prev) => ({ ...prev, [data.doc_id]: data }))
                }
                if (TERMINAL_EVENT_TYPES.has(type)) {
                    source.close()
                }
            })
        })
        source.onerror = () => {
            console.error('run stream connection error')
        }
    }

    // Single place that creates a run and starts streaming it — used both by
    // ActionsTable's start-of-flow "Begin review" button and by Bulk approve's
    // next-run creation, so there's one path to keep the Timeline in sync.
    const createRun = async () => {
        const res = await fetch(`${API_BASE}/runs/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        })
        if (!res.ok) throw new Error(`Failed to create run: ${res.status}`)
        const data = await res.json()
        console.log('created run:', data.run_id)
        startRunStream(data.run_id)
        return data.run_id
    }

    // isCorrected reflects the row's CURRENT state, not a one-way flag — a
    // toggle back to the agent's original value must be able to un-mark a doc
    // as corrected, or its Timeline diamond never reverts to a circle.
    const setDocumentCorrected = (docId, isCorrected) => {
        setCorrectedDocIds((prev) => {
            if (isCorrected === prev.has(docId)) return prev
            const next = new Set(prev)
            if (isCorrected) next.add(docId)
            else next.delete(docId)
            return next
        })
    }

    // Clicking a run's square in the Timeline loads that run's decisions into
    // the Actions Table instead of opening the admin record — filters the
    // already-loaded decision history by run_id, then fetches the full
    // document for each one (same shape the live SSE path already builds).
    const selectRun = (runId) => {
        const runDecisions = dbDecisions.filter((d) => d.run_id === runId)

        setDocuments([])
        setActiveDocument(null)
        setDecisions({})

        Promise.all(
            runDecisions.map((d) =>
                fetch(`${API_BASE}/documents/${d.doc_id}/`).then((res) => res.json())
            )
        )
            .then((docs) => {
                // Set documents and decisions together, in the same batch, so
                // ActionsTable's decisions-merge effect runs against rows that
                // actually exist yet — setting decisions before the rows exist
                // means that effect fires once (over nothing) and never again,
                // leaving Rel/Priv/reasoning blank forever.
                const decisionMap = {}
                runDecisions.forEach((d) => {
                    decisionMap[d.doc_id] = {
                        doc_id: d.doc_id,
                        decision_id: d.decision_id,
                        relevance: d.relevance,
                        privilege: d.privilege,
                        confidence: d.confidence,
                        reasoning: d.reasoning,
                        proposed_by: d.proposed_by,
                    }
                })
                setDocuments(docs)
                setDecisions(decisionMap)
            })
            .catch((err) => console.error('Failed to load documents for run:', err))
    }

    useEffect(() => () => eventSourceRef.current?.close(), [])

    // Loads the durable audit history on screen load, so the Timeline shows
    // every batch/decision/correction ever recorded — not just what's streamed
    // live during the current browser session.
    useEffect(() => {
        if (!selectedCase) return
        Promise.all([
            fetch(`${API_BASE}/runs/all/`).then((res) => res.json()),
            fetch(`${API_BASE}/decisions/all/`).then((res) => res.json()),
            fetch(`${API_BASE}/corrections/all/`).then((res) => res.json()),
        ])
            .then(([runs, decisionRows, correctionRows]) => {
                setDbRuns(runs)
                setDbDecisions(decisionRows)
                setDbCorrections(correctionRows)
            })
            .catch((err) => console.error('Failed to load audit history:', err))
    }, [selectedCase])

    if (selectedCase) {
        return (
            <Container maxWidth="xxl" disableGutters sx={{ height: 'calc(100vh - 65px)', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>
                <Stack direction="row" alignItems="center" spacing={2} sx={{ p: 4, flexShrink: 0 }}>
                    <Typography
                        onClick={() => setSelectedCase(null)}
                        sx={{ color: accent, fontWeight: 700, cursor: 'pointer', display: 'inline-block', '&:hover': { textDecoration: 'underline' } }}
                    >
                        ←
                    </Typography>
                    <Typography variant="h5" sx={{ fontWeight: 700 }}>
                        {selectedCase.emoji} {selectedCase.name}
                    </Typography>
                </Stack>
                <Box
                    sx={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gridTemplateRows: '70% 10% 20%',
                        gridTemplateAreas: `"tl tr" "bl bl" "br br"`,
                        flex: 1,
                        minHeight: 0,
                    }}
                >
                    <ActionsTable
                        documents={documents}
                        decisions={decisions}
                        onSelectDocument={setActiveDocument}
                        onCreateRun={createRun}
                        onDocumentCorrected={setDocumentCorrected}
                        sx={{ gridArea: 'tl' }}
                    />
                    <ActiveDocument document={activeDocument} sx={{ gridArea: 'tr' }} />
                    <Reasoning events={runEvents} sx={{ gridArea: 'bl' }} />
                    <Timeline
                        events={timelineEvents}
                        correctedDocIds={correctedDocIds}
                        dbRuns={dbRuns}
                        dbDecisions={dbDecisions}
                        dbCorrections={dbCorrections}
                        onSelectRun={selectRun}
                        sx={{ gridArea: 'br' }}
                    />
                </Box>
            </Container>
        )
    }

    return (
        <Container maxWidth="md" sx={{ py: 4 }}>
            <Typography variant="h3" sx={{ fontWeight: 800, letterSpacing: '-0.02em', fontSize: { xs: 30, md: 42 }, textAlign: 'center', mb: 3 }}>
                Case List
            </Typography>
            <Grid container spacing={2}>
                {cases.map((c) => (
                    <Grid item key={c.id} xs={12}>
                        <Paper
                            onClick={() => setSelectedCase(c)}
                            sx={{ p: 3, display: 'flex', alignItems: 'center', gap: 3, cursor: 'pointer', minHeight: 160 }}
                        >
                            <Box sx={{ width: 64, height: 64, flexShrink: 0, borderRadius: 2, bgcolor: highlight, display: 'grid', placeItems: 'center', fontSize: 32 }}>
                                {c.emoji}
                            </Box>
                            <Box>
                                <Typography fontWeight={600} fontSize={20}>{c.name}</Typography>
                                <Typography variant="body2" color="text.secondary">{c.type}</Typography>
                                <Typography variant="caption" color="text.secondary">{c.status}</Typography>
                            </Box>
                        </Paper>
                    </Grid>
                ))}
            </Grid>
        </Container>
    )
}
