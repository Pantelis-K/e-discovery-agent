import React from 'react'
import { Box, Typography, useTheme } from '@mui/material'

export default function Timeline({ caseItem, sx }) {
    const theme = useTheme()
    const { muted } = theme.palette.brand
    const border = theme.palette.divider

    return (
        <Box sx={{ border: `1px solid ${border}`, bgcolor: '#fff', p: 3, ...sx }}>
            <Typography sx={{ fontWeight: 700, color: muted, fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.05em', mb: 1 }}>
                Timeline
            </Typography>
        </Box>
    )
}
