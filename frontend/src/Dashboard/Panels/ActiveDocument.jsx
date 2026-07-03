import React from 'react'
import { Avatar, Box, Chip, Divider, Stack, Typography, useTheme } from '@mui/material'
import AttachFileIcon from '@mui/icons-material/AttachFile'

const SAMPLE_EMAIL = {
    from: { name: 'David Okonkwo', address: 'd.okonkwo@penningtonvance.com' },
    to: ['legal-team@penningtonvance.com'],
    cc: ['s.reyes@penningtonvance.com'],
    subject: 'RE: Meridian Foods — supply contract renewal terms',
    date: 'Tue, 14 Jan 2025, 09:42 AM',
    body: `Hi team,

Following up on our call yesterday — Meridian is pushing back on the indemnification clause again. Their outside counsel flagged section 8.3 as "commercially unreasonable" and wants a cap tied to the annual contract value rather than an uncapped exposure.

I think we can live with a cap, but only if we get the audit-rights language back in exchange. Can someone pull the redline from the last round before EOD? I'd like to get a revised draft to them by Thursday.

Also — heads up that finance wants to be looped in before we agree to anything on payment terms, so let's keep this thread tight until we've synced with them.

Thanks,
David`,
    attachments: ['Draft_Amendment_v3.docx'],
}

export default function ActiveDocument({ caseItem, sx }) {
    const theme = useTheme()
    const { muted, accent } = theme.palette.brand
    const border = theme.palette.divider
    const email = SAMPLE_EMAIL

    return (
        <Box sx={{ border: `1px solid ${border}`, bgcolor: '#fff', p: 3, display: 'flex', flexDirection: 'column', overflow: 'hidden', ...sx }}>
            <Typography sx={{ fontWeight: 700, color: muted, fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.05em', mb: 1.5, flexShrink: 0, textAlign: 'center' }}>
                Active Document
            </Typography>

            <Box sx={{ flexShrink: 0 }}>
                <Typography sx={{ fontWeight: 700, fontSize: 16, mb: 1.5 }}>{email.subject}</Typography>
                <Stack direction="row" spacing={1.5} alignItems="flex-start">
                    <Avatar sx={{ bgcolor: accent, width: 36, height: 36, fontSize: 14 }}>
                        {email.from.name.split(' ').map((n) => n[0]).join('')}
                    </Avatar>
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                        <Stack direction="row" justifyContent="space-between" alignItems="baseline">
                            <Typography sx={{ fontWeight: 600, fontSize: 14 }}>
                                {email.from.name} <Typography component="span" sx={{ color: muted, fontSize: 13 }}>&lt;{email.from.address}&gt;</Typography>
                            </Typography>
                            <Typography sx={{ color: muted, fontSize: 12, flexShrink: 0, ml: 1 }}>{email.date}</Typography>
                        </Stack>
                        <Typography sx={{ color: muted, fontSize: 12.5 }}>To: {email.to.join(', ')}</Typography>
                        {email.cc.length > 0 && (
                            <Typography sx={{ color: muted, fontSize: 12.5 }}>Cc: {email.cc.join(', ')}</Typography>
                        )}
                    </Box>
                </Stack>
            </Box>

            <Divider sx={{ my: 2, flexShrink: 0 }} />

            <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
                <Typography sx={{ fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                    {email.body}
                </Typography>
            </Box>

            {email.attachments.length > 0 && (
                <Stack direction="row" spacing={1} sx={{ pt: 2, flexShrink: 0 }}>
                    {email.attachments.map((name) => (
                        <Chip key={name} size="small" icon={<AttachFileIcon sx={{ fontSize: 14 }} />} label={name} variant="outlined" />
                    ))}
                </Stack>
            )}
        </Box>
    )
}
