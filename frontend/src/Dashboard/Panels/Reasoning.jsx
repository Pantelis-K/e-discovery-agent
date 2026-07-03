import React, { useEffect, useState } from 'react'
import { Box, Typography, useTheme } from '@mui/material'

const ITEM_HEIGHT = 28

const PROCESSING_TERMS = [
    'Parsing custodian metadata…',
    'Cross-referencing privilege log…',
    'Scanning for PII patterns…',
    'Evaluating relevance signals…',
    'Weighing precedent from prior productions…',
    'Checking responsive keyword hits…',
    'Flagging potential hot documents…',
    'Synthesizing reasoning trace…',
]

export default function Reasoning({ caseItem, sx }) {
    const theme = useTheme()
    const { muted, accent } = theme.palette.brand
    const border = theme.palette.divider
    const [index, setIndex] = useState(0)

    useEffect(() => {
        const id = setInterval(() => {
            setIndex((i) => (i + 1) % PROCESSING_TERMS.length)
        }, 1800)
        return () => clearInterval(id)
    }, [])

    return (
        <Box sx={{ border: `1px solid ${border}`, bgcolor: '#fff', p: 2, display: 'flex', flexDirection: 'column', ...sx }}>
            <Box sx={{ height: ITEM_HEIGHT, overflow: 'hidden' }}>
                <Box sx={{ transform: `translateY(-${index * ITEM_HEIGHT}px)`, transition: 'transform 0.5s ease' }}>
                    {PROCESSING_TERMS.map((term) => (
                        <Box key={term} sx={{ height: ITEM_HEIGHT, display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Typography
                                sx={{
                                    fontFamily: 'monospace',
                                    fontSize: 13,
                                    whiteSpace: 'nowrap',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                }}
                            >
                                {term}
                            </Typography>
                        </Box>
                    ))}
                </Box>
            </Box>
        </Box>
    )
}
