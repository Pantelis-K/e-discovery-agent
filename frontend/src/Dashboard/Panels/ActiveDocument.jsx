import React from 'react'
import { Avatar, Box, Stack, Typography, useTheme } from '@mui/material'

function initials(label) {
    const letters = (label || '').split(' ').filter(Boolean).map((w) => w[0])
    return letters.slice(0, 2).join('').toUpperCase() || '?'
}

export default function ActiveDocument({ document, sx }) {
    const theme = useTheme()
    const { muted, accent } = theme.palette.brand
    const border = theme.palette.divider

    const from = document?.from_display
    const to = document?.to_display || []
    const cc = document?.cc_display || []
    const fromLabel = from?.display || '(unknown sender)'

    return (
        <Box sx={{ border: `1px solid ${border}`, bgcolor: '#fff', p: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', ...sx }}>
            <Typography sx={{ fontWeight: 700, color: muted, fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.05em', mb: 1.5, flexShrink: 0, textAlign: 'center' }}>
                Active Document
            </Typography>

            {!document ? (
                <Box sx={{ flex: 1, display: 'grid', placeItems: 'center' }}>
                    <Typography sx={{ color: muted, fontSize: 13 }}>
                        Select a document from the table to preview it here.
                    </Typography>
                </Box>
            ) : (
                <>
                    <Box sx={{ flexShrink: 0 }}>
                        <Typography sx={{ fontWeight: 700, fontSize: 16, mb: 1.5 }}>
                            {document.subject || '(no subject)'}
                        </Typography>
                        <Stack direction="row" spacing={1.5} alignItems="flex-start">
                            <Avatar sx={{ bgcolor: accent, width: 36, height: 36, fontSize: 14 }}>
                                {initials(fromLabel)}
                            </Avatar>
                            <Box sx={{ minWidth: 0, flex: 1 }}>
                                <Typography sx={{ fontWeight: 600, fontSize: 14 }}>
                                    {fromLabel}
                                    {from?.email && (
                                        <Typography component="span" sx={{ color: muted, fontSize: 13 }}> &lt;{from.email}&gt;</Typography>
                                    )}
                                </Typography>
                                <Typography sx={{ color: muted, fontSize: 12.5 }}>
                                    To: {to.length > 0 ? to.map((u) => u.display).join(', ') : '(unknown recipients)'}
                                </Typography>
                                {cc.length > 0 && (
                                    <Typography sx={{ color: muted, fontSize: 12.5 }}>
                                        Cc: {cc.map((u) => u.display).join(', ')}
                                    </Typography>
                                )}
                            </Box>
                        </Stack>
                    </Box>

                    <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto', mt: 2 }}>
                        <Typography sx={{ fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                            {document.body || ''}
                        </Typography>
                    </Box>
                </>
            )}
        </Box>
    )
}
