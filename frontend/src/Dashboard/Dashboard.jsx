import React, { useState } from 'react'
import { Container, Grid, Paper, Typography, Box, useTheme, Stack } from '@mui/material'
import ActionsTable from './Panels/ActionsTable'
import TopRight from './Panels/ActiveDocument'
import BottomLeft from './Panels/Reasoning'
import BottomRight from './Panels/Timeline'

export default function Dashboard({ cases }) {
    const [selectedCase, setSelectedCase] = useState(null)
    const theme = useTheme()
    const { palette } = theme
    const { accent, highlight } = palette.brand

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
                    <ActionsTable caseItem={selectedCase} sx={{ gridArea: 'tl' }} />
                    <TopRight caseItem={selectedCase} sx={{ gridArea: 'tr' }} />
                    <BottomLeft caseItem={selectedCase} sx={{ gridArea: 'bl' }} />
                    <BottomRight caseItem={selectedCase} sx={{ gridArea: 'br' }} />
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
