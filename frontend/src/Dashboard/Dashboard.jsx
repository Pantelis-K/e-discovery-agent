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
    const [runEvents, setRunEvents] = useState([])
    const eventSourceRef = useRef(null)
    const theme = useTheme()
    const { palette } = theme
    const { accent, highlight } = palette.brand

    const startRunStream = (runId) => {
        eventSourceRef.current?.close()
        setRunEvents([])

        const source = new EventSource(`${API_BASE}/runs/${runId}/stream/`)
        eventSourceRef.current = source

        RUN_EVENT_TYPES.forEach((type) => {
            source.addEventListener(type, (e) => {
                const data = e.data ? JSON.parse(e.data) : {}
                setRunEvents((prev) => [...prev, { type, data }])
                if (TERMINAL_EVENT_TYPES.has(type)) {
                    source.close()
                }
            })
        })
        source.onerror = () => {
            console.error('run stream connection error')
        }
    }

    useEffect(() => () => eventSourceRef.current?.close(), [])

    useEffect(() => {
        if (!selectedCase) return

        let cancelled = false

        fetch(`${API_BASE}/documents/batch/`)
            .then((res) => {
                if (!res.ok) throw new Error(`Failed to fetch document batch: ${res.status}`)
                return res.json()
            })
            .then((data) => {
                console.log('document batch:', data)
                if (cancelled) return
                setDocuments(data)
                setActiveDocument((prev) => prev ?? data[0] ?? null)
            })
            .catch((err) => console.error('Failed to load document batch:', err))

        return () => {
            cancelled = true
        }
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
                        onSelectDocument={setActiveDocument}
                        onRunStarted={startRunStream}
                        sx={{ gridArea: 'tl' }}
                    />
                    <ActiveDocument document={activeDocument} sx={{ gridArea: 'tr' }} />
                    <Reasoning events={runEvents} sx={{ gridArea: 'bl' }} />
                    <Timeline sx={{ gridArea: 'br' }} />
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
