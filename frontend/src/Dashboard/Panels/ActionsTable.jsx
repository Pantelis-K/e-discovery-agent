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

const REASONING_WORDS = [
    'references', 'custodian', 'communications', 'regarding', 'the', 'disputed',
    'contract', 'terms', 'and', 'potential', 'breach', 'timeline', 'discussed',
    'internally', 'between', 'counsel', 'and', 'finance', 'team', 'ahead', 'of',
    'the', 'quarterly', 'review',
]

function randomReasoning() {
    const length = 5 + Math.floor(Math.random() * 4)
    const words = Array.from({ length }, () => REASONING_WORDS[Math.floor(Math.random() * REASONING_WORDS.length)])
    return words.join(' ')
}

function buildRows() {
    return Array.from({ length: 25 }).map((_, i) => ({
        id: i + 1,
        document: `Document_${i + 1}.pdf`,
        doc: {
            doc_id: `Document_${i + 1}.pdf`,
            subject: `Document_${i + 1}.pdf`,
            body: '(placeholder row — real document batch not loaded yet)',
            from_display: null,
            to_display: [],
            cc_display: [],
        },
        relevant: false,
        privileged: false,
        reasoning: randomReasoning(),
        actioned: false,
    }))
}

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

function buildRowsFromDocuments(documents) {
    return documents.map((doc, i) => ({
        id: i + 1,
        document: documentLabel(doc),
        doc,
        relevant: false,
        privileged: false,
        reasoning: '',
        actioned: false,
    }))
}

const API_BASE = 'http://localhost:8000/api'

export default function ActionsTable({ documents, onSelectDocument, onRunStarted, sx }) {
    const theme = useTheme()
    const { muted } = theme.palette.brand
    const border = theme.palette.divider
    // Mock placeholder rows until the real document batch arrives.
    const [rows, setRows] = useState(buildRows)
    // Keyed by row id so repeated edits to the same row collapse into one
    // entry holding its current state, not a history of every keystroke.
    const [changes, setChanges] = useState({})

    useEffect(() => {
        if (documents && documents.length > 0) {
            setRows(buildRowsFromDocuments(documents))
            setChanges({})
        }
    }, [documents])

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
                },
            }))
            return next
        })
    }

    const bulkApprove = async () => {
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
