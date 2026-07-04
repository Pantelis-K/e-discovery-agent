import React, { useEffect, useState } from 'react'
import { Box, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography, useTheme } from '@mui/material'
import ActionsTableRow from './ActionsTableRow'

const COLUMNS = [
    { label: 'Document', align: 'left', width: 275 },
    { label: 'Rel', align: 'center', width: 50 },
    { label: 'Priv', align: 'center', width: 50 },
    { label: 'Reasoning', align: 'left' },
    { label: '', align: 'center', width: 100 },
]

const SUBJECT_MAX_LENGTH = 30
const DOC_ID_MAX_LENGTH = 24

function truncate(str, maxLength) {
    if (!str || str.length <= maxLength) return str
    return `${str.slice(0, maxLength - 1)}…`
}

function documentLabel(doc) {
    if (doc.subject) return truncate(doc.subject, SUBJECT_MAX_LENGTH)
    return `${truncate(doc.doc_id, DOC_ID_MAX_LENGTH)}`
}

function rowFromDocument(doc) {
    return {
        id: doc.doc_id,
        document: documentLabel(doc),
        doc,
        relevant: false,
        privileged: false,
        reasoning: '',
        actioned: false,
        // Rel/Priv stay locked until the LLM proposes a decision for this doc.
        hasDecision: false,
        // Snapshot of the LLM's proposal, frozen once set — this is the
        // Correction.original_value a later reviewer edit is measured against.
        original: null,
    }
}

const API_BASE = 'http://localhost:8000/api'

export default function ActionsTable({ documents, decisions, onSelectDocument, onRunStarted, sx }) {
    const theme = useTheme()
    const { muted } = theme.palette.brand
    const border = theme.palette.divider
    // Starts empty — rows are added one at a time as doc_ids stream in from the
    // active run (see Dashboard's fetchAndAddDocument), not pre-loaded in bulk.
    const [rows, setRows] = useState([])
    // Flips the instant the start-of-flow button is clicked — independent of
    // `rows` so the button disappears immediately, not once the first document
    // actually arrives over SSE.
    const [started, setStarted] = useState(false)
    // Keyed by row id so repeated edits to the same row collapse into one
    // entry holding its current state, not a history of every keystroke.
    const [changes, setChanges] = useState({})

    useEffect(() => {
        if (!documents || documents.length === 0) {
            setRows([])
            return
        }
        setRows((prev) => {
            const existingIds = new Set(prev.map((row) => row.doc.doc_id))
            const newRows = documents.filter((doc) => !existingIds.has(doc.doc_id)).map(rowFromDocument)
            return newRows.length > 0 ? [...prev, ...newRows] : prev
        })
    }, [documents])

    // Reflects the agent's own proposed relevance/privilege/reasoning as
    // document_decision_proposed events arrive, and unlocks the Rel/Priv
    // buttons. Not a reviewer edit, so this never touches `changes` (the
    // corrections payload) — but it does freeze `original`, the baseline a
    // later reviewer edit is measured against.
    useEffect(() => {
        if (!decisions || Object.keys(decisions).length === 0) return
        setRows((prev) => prev.map((row) => {
            const decision = decisions[row.doc.doc_id]
            if (!decision) return row
            const relevant = !!decision.relevance
            const privileged = decision.privilege === 'privileged'
            const reasoning = decision.reasoning || ''
            if (row.hasDecision && row.relevant === relevant && row.privileged === privileged && row.reasoning === reasoning) {
                return row
            }
            return {
                ...row,
                relevant,
                privileged,
                reasoning,
                hasDecision: true,
                decision_id: decision.decision_id,
                original: { relevant, privileged, reasoning },
            }
        }))
    }, [decisions])

    const updateRow = (id, fieldChanges) => {
        setRows((prev) => {
            const next = prev.map((row) => (row.id === id ? { ...row, ...fieldChanges } : row))
            const updated = next.find((row) => row.id === id)
            setChanges((prevChanges) => ({
                ...prevChanges,
                [id]: {
                    doc_id: updated.doc.doc_id,
                    relevant: updated.relevant,
                    privileged: updated.privileged,
                    reasoning: updated.reasoning,
                    ...(updated.original ? { original: updated.original } : {}),
                },
            }))
            return next
        })
    }

    const beginReview = async () => {
        setStarted(true)
        try {
            const res = await fetch(`${API_BASE}/runs/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            })
            if (!res.ok) throw new Error(`Failed to create run: ${res.status}`)
            const data = await res.json()
            console.log('created run:', data.run_id)
            onRunStarted?.(data.run_id)
            setChanges({})
        } catch (err) {
            console.error('Bulk approve failed to create run:', err)
            return
        }
        setRows((prev) => prev.map((row) => ({ ...row, actioned: true })))
    }
    
    const bulkApprove = async () => {
        setStarted(true)

        const toCommit = rows
            .filter((row) => row.hasDecision && row.decision_id != null)
            .map((row) => ({ doc_id: row.doc.doc_id, decision_id: row.decision_id }))
        if (toCommit.length > 0) {
            try {
                const res = await fetch(`${API_BASE}/decisions/bulk_commit/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(toCommit),
                })
                if (!res.ok) throw new Error(`Failed to commit decisions: ${res.status}`)
                const data = await res.json()
                console.log('committed decisions:', data.committed)
            } catch (err) {
                console.error('Bulk approve failed to commit decisions:', err)
            }
        }

        const toSubmit = Object.values(changes)
        if (toSubmit.length > 0) {
            try {
                const res = await fetch(`${API_BASE}/corrections/bulk/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(toSubmit),
                })
                if (!res.ok) throw new Error(`Failed to submit corrections: ${res.status}`)
                const data = await res.json()
                console.log('submitted corrections:', data.created)
                setChanges({})
            } catch (err) {
                console.error('Bulk approve failed to submit corrections:', err)
            }
        }

        try {
            const res = await fetch(`${API_BASE}/runs/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            })
            if (!res.ok) throw new Error(`Failed to create run: ${res.status}`)
            const data = await res.json()
            console.log('created run:', data.run_id)
            onRunStarted?.(data.run_id)
        } catch (err) {
            console.error('Bulk approve failed to create run:', err)
            return
        }
        setRows((prev) => prev.map((row) => ({ ...row, actioned: true })))
    }

    return (
        <Box sx={{ border: `1px solid ${border}`, bgcolor: '#fff', p: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', ...sx }}>
            <TableContainer sx={{ flex: 1, overflow: 'auto' }}>
                <Table size="small" stickyHeader sx={{ tableLayout: 'fixed', '& .MuiTableCell-root': { boxSizing: 'border-box' } }}>
                    <TableHead>
                        <TableRow>
                            {COLUMNS.map((col) => (
                                <TableCell
                                    key={col.label || 'actioned'}
                                    align={col.align}
                                    sx={{
                                        fontWeight: 700,
                                        fontSize: 12,
                                        color: muted,
                                        textTransform: 'uppercase',
                                        letterSpacing: '0.04em',
                                        width: col.width,
                                        ...(col.width ? { px: 0 } : {}),
                                        ...(col.label === 'Reasoning' ? { pl: 3 } : {}),
                                        ...(col.label === '' ? { maxWidth: 100 } : {}),
                                    }}
                                >
                                    {col.label || (
                                        <Button
                                            size="small"
                                            variant="text"
                                            onClick={bulkApprove}
                                            sx={{ minWidth: 0, px: 1, textTransform: 'none' }}
                                        >
                                            Bulk approve
                                        </Button>
                                    )}
                                </TableCell>
                            ))}
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {!started && (
                            <TableRow>
                                <TableCell colSpan={COLUMNS.length} align="center" sx={{ py: 4 }}>
                                    <Button variant="contained" onClick={beginReview} sx={{ textTransform: 'none' }}>
                                        Begin review
                                    </Button>
                                </TableCell>
                            </TableRow>
                        )}
                        {rows.map((row) => (
                            <ActionsTableRow
                                key={row.id}
                                row={row}
                                onChange={(fieldChanges) => updateRow(row.id, fieldChanges)}
                                onSelectDocument={onSelectDocument}
                            />
                        ))}
                    </TableBody>
                </Table>
            </TableContainer>
        </Box>
    )
}
