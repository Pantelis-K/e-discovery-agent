import React, { useState } from 'react'
import { Box, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography, useTheme } from '@mui/material'
import ActionsTableRow from './ActionsTableRow'

const COLUMNS = [
    { label: 'Document', align: 'left', width: 220 },
    { label: 'Rel', align: 'center', width: 50 },
    { label: 'Priv', align: 'center', width: 50 },
    { label: 'Reasoning', align: 'left' },
    { label: '', align: 'center', width: 50 },
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

export default function ActionsTable({ caseItem, sx }) {
    const theme = useTheme()
    const { muted } = theme.palette.brand
    const border = theme.palette.divider
    const [rows, setRows] = useState(buildRows)

    const updateRow = (id, changes) => {
        setRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...changes } : row)))
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
                                    }}
                                >
                                    {col.label}
                                </TableCell>
                            ))}
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {rows.map((row) => (
                            <ActionsTableRow key={row.id} row={row} onChange={(changes) => updateRow(row.id, changes)} />
                        ))}
                    </TableBody>
                </Table>
            </TableContainer>
        </Box>
    )
}
