import React, { useState } from 'react'
import { Box, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography, useTheme } from '@mui/material'
import ActionsTableRow from './ActionsTableRow'

const COLUMNS = [
    { label: 'Document', align: 'left', width: 220 },
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
        relevant: false,
        privileged: false,
        reasoning: randomReasoning(),
        actioned: false,
    }))
}

const API_BASE = 'http://localhost:8000/api'

export default function ActionsTable({ caseItem, sx }) {
    const theme = useTheme()
    const { muted } = theme.palette.brand
    const border = theme.palette.divider
    const [rows, setRows] = useState(buildRows)
    // Keyed by row id so repeated edits to the same row collapse into one
    // entry holding its current state, not a history of every keystroke.
    const [changes, setChanges] = useState({})

    const updateRow = (id, fieldChanges) => {
        setRows((prev) => {
            const next = prev.map((row) => (row.id === id ? { ...row, ...fieldChanges } : row))
            const updated = next.find((row) => row.id === id)
            setChanges((prevChanges) => ({
                ...prevChanges,
                [id]: {
                    doc_id: updated.document,
                    relevant: updated.relevant,
                    privileged: updated.privileged,
                    reasoning: updated.reasoning,
                },
            }))
            return next
        })
    }

    const bulkApprove = async () => {
        const payload = Object.values(changes)
        if (payload.length > 0) {
            try {
                const res = await fetch(`${API_BASE}/corrections/bulk/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                })
                if (!res.ok) throw new Error(`Bulk approve failed: ${res.status}`)
                setChanges({})
            } catch (err) {
                console.error('Bulk approve failed to submit corrections:', err)
                return
            }
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
                            <ActionsTableRow key={row.id} row={row} onChange={(fieldChanges) => updateRow(row.id, fieldChanges)} />
                        ))}
                    </TableBody>
                </Table>
            </TableContainer>
        </Box>
    )
}
