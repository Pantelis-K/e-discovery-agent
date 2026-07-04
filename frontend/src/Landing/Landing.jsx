import React, { useState, useEffect } from 'react'
import {
    Box, Button, Container, Typography, Stack,
    Card, CardContent, Avatar, Rating, Divider, Chip, useMediaQuery
} from '@mui/material'
import { keyframes, useTheme } from '@mui/system'
import { useNavigate } from 'react-router-dom'

// ── Easter-egg config ────────────────────────────────────────────────
// How far (in viewport heights) the user can scroll before we "catch" them.
const CATCH_AFTER_PAGES = 2

// ── Brand tokens ─────────────────────────────────────────────────────
// shared by theme palette now; kept locally only for existing inline icons.
const ACCENT = '#3B4CCA'
const GOLD = '#E0A82E'

// ── Animations ───────────────────────────────────────────────────────
const bounce = keyframes`
    0%, 100% { transform: translateY(0) rotate(-4deg); }
    50%      { transform: translateY(-22px) rotate(4deg); }
`
const float = keyframes`
    0%, 100% { transform: translateY(0); opacity: 0.7; }
    50%      { transform: translateY(-12px); opacity: 1; }
`
const pop = keyframes`
    from { transform: scale(0.9); opacity: 0; }
    to   { transform: scale(1);   opacity: 1; }
`

// ── Tiny inline SVG icons (no icon dependency) ───────────────────────
const iconProps = { width: 22, height: 22, fill: 'none', stroke: ACCENT, strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }
const ShieldIcon = () => (<svg viewBox="0 0 24 24" {...iconProps}><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" /><path d="M9 12l2 2 4-4" /></svg>)
const BoltIcon = () => (<svg viewBox="0 0 24 24" {...iconProps}><path d="M13 3L5 13h5l-1 8 8-11h-5l1-7z" /></svg>)
const LayersIcon = () => (<svg viewBox="0 0 24 24" {...iconProps}><path d="M12 3l9 5-9 5-9-5 9-5z" /><path d="M3 13l9 5 9-5" /></svg>)

const FIRMS = ['HARROW & BLACKWOOD', 'KESSLER STEIN', 'PENNINGTON VANCE', 'ALDRIDGE & CROWE', 'MARCHETTI LEGAL']

const STATS = [
    { value: '40M+', label: 'documents reviewed' },
    { value: '92%', label: 'faster first-pass review' },
    { value: '6wk → 4d', label: 'average matter turnaround' },
    { value: 'SOC 2', label: 'Type II certified' },
]

const FEATURES = [
    { icon: <ShieldIcon />, title: 'Agentic first-pass review', body: 'An autonomous loop reads every document, proposes a relevance call, and cites its reasoning — so your team reviews decisions, not haystacks.' },
    { icon: <BoltIcon />, title: 'Privilege & PII detection', body: 'Surfaces privileged material, PII, and hot documents before they ever reach production or opposing counsel.' },
    { icon: <LayersIcon />, title: 'Human-in-the-loop, always', body: 'One-click accept, override, or escalate. Every model decision is logged for defensibility and audit.' },
]

const TESTIMONIALS = [
    { quote: 'We cut first-pass review from six weeks to four days. My associates actually thank me now.', name: 'Naomi Reyes', role: 'Director of Litigation Support', firm: 'Harrow & Blackwood LLP' },
    { quote: 'It flags privilege issues we’d have missed at 2am on a Friday. Closest thing to a good night’s sleep we’ve had in years.', name: 'David Okonkwo', role: 'Partner', firm: 'Pennington Vance' },
    { quote: 'Onboarded in an afternoon, passed our security review, and our GC stopped asking why discovery costs so much.', name: 'Priya Anand', role: 'eDiscovery Lead', firm: 'Kessler Stein' },
]

export default function Landing() {
    const navigate = useNavigate()
    const theme = useTheme()
    const { palette } = theme
    const { accent, ink, muted, soft, highlight, gold } = palette.brand
    const border = palette.divider
    const isMobile = useMediaQuery(theme.breakpoints.down('md'))
    const [caught, setCaught] = useState(false)

    // Watch scroll depth
    useEffect(() => {
        const onScroll = () => {
            if (window.scrollY > window.innerHeight * CATCH_AFTER_PAGES) setCaught(true)
        }
        window.addEventListener('scroll', onScroll, { passive: true })
        return () => window.removeEventListener('scroll', onScroll)
    }, [])

    // Lock body scroll while caught
    useEffect(() => {
        document.body.style.overflow = caught ? 'hidden' : ''
        return () => { document.body.style.overflow = '' }
    }, [caught])

    const handleBack = () => {
        window.scrollTo({ top: 0, behavior: 'auto' })
        setCaught(false)
    }

    return (
        <Box sx={{ bgcolor: palette.background.paper, color: ink }}>
            {/* ── Nav ─────────────────────────────────────────────── */}
            

            {/* ── Hero ────────────────────────────────────────────── */}
            <Box sx={{ background: `radial-gradient(1000px 400px at 50% -50px, #EEF1FF, #fff)` }}>
                <Container maxWidth="md" sx={{ pt: { xs: 8, md: 12 }, pb: { xs: 8, md: 10 }, textAlign: 'center' }}>
                    <Chip label="AI-native e-discovery" size="small" sx={{ bgcolor: highlight, color: accent, fontWeight: 600, mb: 3 }} />
                    <Typography variant="h2" sx={{ fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.05, fontSize: { xs: 40, md: 60 } }}>
                        Turn millions of documents<br />into a decision, not a project.
                    </Typography>
                    <Typography sx={{ color: muted, fontSize: { xs: 17, md: 20 }, mt: 3, maxWidth: 620, mx: 'auto' }}>
                        FunkE runs an autonomous review loop across your entire discovery set, ranks relevance, and hands your team defensible, one-click calls.
                    </Typography>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center" sx={{ mt: 4 }}>
                        <Button variant="contained" size="large" onClick={() => navigate('/login')} disableElevation sx={{ bgcolor: accent, px: 4, '&:hover': { bgcolor: theme.palette.primary.dark } }}>Get started</Button>
                        <Button variant="outlined" size="large" onClick={() => navigate('/contact')} sx={{ borderColor: border, color: ink, px: 4 }}>Book a demo</Button>
                    </Stack>
                    <Typography sx={{ color: muted, fontSize: 13, mt: 2 }}>
                        Demo mode — “Get started” routes straight to the dashboard.
                    </Typography>
                </Container>
            </Box>

            {/* ── Trust logos ─────────────────────────────────────── */}
            <Container maxWidth="lg" sx={{ py: 5 }}>
                <Typography sx={{ textAlign: 'center', color: muted, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', mb: 3 }}>
                    Trusted by litigation teams at
                </Typography>
                <Stack direction="row" spacing={{ xs: 3, md: 5 }} justifyContent="center" flexWrap="wrap" useFlexGap sx={{ opacity: 0.55 }}>
                    {FIRMS.map(f => (
                        <Typography key={f} sx={{ fontWeight: 700, letterSpacing: '0.06em', fontSize: { xs: 12, md: 15 }, color: ink }}>{f}</Typography>
                    ))}
                </Stack>
            </Container>

            {/* ── Stats ───────────────────────────────────────────── */}
            <Box sx={{ bgcolor: ink, color: '#fff', py: 6 }}>
                <Container maxWidth="lg">
                    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 4, textAlign: 'center' }}>
                        {STATS.map(s => (
                            <Box key={s.label}>
                                <Typography sx={{ fontSize: { xs: 30, md: 40 }, fontWeight: 800, letterSpacing: '-0.02em' }}>{s.value}</Typography>
                                <Typography sx={{ color: muted, fontSize: 14 }}>{s.label}</Typography>
                            </Box>
                        ))}
                    </Box>
                </Container>
            </Box>

            {/* ── Features ────────────────────────────────────────── */}
            <Container maxWidth="lg" sx={{ py: { xs: 8, md: 12 } }}>
                <Typography variant="h3" sx={{ fontWeight: 800, letterSpacing: '-0.02em', fontSize: { xs: 30, md: 42 }, textAlign: 'center', mb: 1 }}>
                    Built for the way discovery actually works
                </Typography>
                <Typography sx={{ color: muted, textAlign: 'center', maxWidth: 560, mx: 'auto', mb: 6 }}>
                    Not another keyword search. A reviewing agent that reasons, cites, and defers to your team.
                </Typography>
                <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 3 }}>
                    {FEATURES.map(f => (
                        <Card key={f.title} elevation={0} sx={{ border: `1px solid ${border}`, borderRadius: 3, p: 1, height: '100%' }}>
                            <CardContent>
                                <Box sx={{ width: 46, height: 46, borderRadius: 2, bgcolor: highlight, display: 'grid', placeItems: 'center', mb: 2 }}>{f.icon}</Box>
                                <Typography sx={{ fontWeight: 700, fontSize: 18, mb: 1 }}>{f.title}</Typography>
                                <Typography sx={{ color: muted, fontSize: 15, lineHeight: 1.6 }}>{f.body}</Typography>
                            </CardContent>
                        </Card>
                    ))}
                </Box>
            </Container>

            {/* ── Testimonials ────────────────────────────────────── */}
            <Box sx={{ bgcolor: soft, py: { xs: 8, md: 12 } }}>
                <Container maxWidth="lg">
                    <Typography variant="h3" sx={{ fontWeight: 800, letterSpacing: '-0.02em', fontSize: { xs: 28, md: 38 }, textAlign: 'center', mb: 6 }}>
                        Loved by the people who bill by the hour
                    </Typography>
                    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 3 }}>
                        {TESTIMONIALS.map(t => (
                            <Card key={t.name} elevation={0} sx={{ border: `1px solid ${border}`, borderRadius: 3, bgcolor: '#fff' }}>
                                <CardContent sx={{ p: 3 }}>
                                    <Rating value={5} readOnly size="small" sx={{ color: gold, mb: 1.5 }} />
                                    <Typography sx={{ fontSize: 16, lineHeight: 1.6, mb: 3 }}>“{t.quote}”</Typography>
                                    <Divider sx={{ mb: 2 }} />
                                    <Stack direction="row" spacing={1.5} alignItems="center">
                                        <Avatar sx={{ bgcolor: ACCENT, width: 40, height: 40, fontSize: 15 }}>{t.name.split(' ').map(n => n[0]).join('')}</Avatar>
                                        <Box>
                                            <Typography sx={{ fontWeight: 700, fontSize: 14 }}>{t.name}</Typography>
                                            <Typography sx={{ color: muted, fontSize: 13 }}>{t.role}, {t.firm}</Typography>
                                        </Box>
                                    </Stack>
                                </CardContent>
                            </Card>
                        ))}
                    </Box>
                </Container>
            </Box>

            {/* ── CTA ─────────────────────────────────────────────── */}
            <Container maxWidth="md" sx={{ py: { xs: 8, md: 12 }, textAlign: 'center' }}>
                <Typography variant="h3" sx={{ fontWeight: 800, letterSpacing: '-0.02em', fontSize: { xs: 30, md: 44 }, mb: 2 }}>
                    See your first matter reviewed in an afternoon
                </Typography>
                <Typography sx={{ color: muted, mb: 4 }}>No rip-and-replace. Point FunkE at a dataset and watch the queue empty.</Typography>
                <Button variant="contained" size="large" onClick={() => navigate('/login')} disableElevation sx={{ bgcolor: ACCENT, textTransform: 'none', fontWeight: 700, borderRadius: 2, px: 5, py: 1.4, '&:hover': { bgcolor: '#2E3CA8' } }}>Get started</Button>
            </Container>

            {/* ── Footer ──────────────────────────────────────────── */}
            <Box sx={{ borderTop: `1px solid ${border}`, py: 4 }}>
                <Container maxWidth="lg">
                    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems="center" spacing={2}>
                        <Typography sx={{ color: muted, fontSize: 13 }}>© {new Date().getFullYear()} FunkE Inc. All rights reserved.</Typography>
                        <Stack direction="row" spacing={3}>
                            {['Privacy', 'Terms', 'Security', 'Status'].map(l => (
                                <Typography key={l} sx={{ color: muted, fontSize: 13, cursor: "pointer", "&:hover": { color: ink } }}>{l}</Typography>
                            ))}
                        </Stack>
                    </Stack>
                </Container>
            </Box>

            {/* ── Easter egg overlay ──────────────────────────────── */}
            {caught && (
                <Box sx={{
                    position: 'fixed', inset: 0, zIndex: 2000,
                    background: `radial-gradient(700px 500px at 50% 40%, #EEF1FF, #fff)`,
                    display: 'grid', placeItems: 'center', p: 3,
                    animation: `${pop} 0.35s ease-out`,
                }}>
                    <Box sx={{ textAlign: 'center', maxWidth: 460 }}>
                        <Box sx={{ position: 'relative', height: 120, mb: 1 }}>
                            <Typography sx={{ fontSize: 88, animation: `${bounce} 1.4s ease-in-out infinite`, display: 'inline-block' }}>🙈</Typography>
                            <Typography sx={{ position: 'absolute', top: 8, left: '30%', fontSize: 26, animation: `${float} 2s ease-in-out infinite` }}>✨</Typography>
                            <Typography sx={{ position: 'absolute', top: 20, right: '30%', fontSize: 20, animation: `${float} 2.4s ease-in-out infinite 0.3s` }}>✨</Typography>
                        </Box>
                        <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: '-0.02em', mb: 1.5 }}>
                            Oops — you caught us!
                        </Typography>
                        <Typography sx={{ color: muted, fontSize: 17, lineHeight: 1.6, mb: 4 }}>
                            There’s no more page down here. FunkE isn’t a real product — it’s a hackathon demo, and the quotes above are (lovingly) made up. The agent behind it, though? Very real. Go try it.
                        </Typography>
                        <Button variant="contained" onClick={handleBack} disableElevation sx={{ bgcolor: accent, borderRadius: 2, px: 4, py: 1.2, '&:hover': { bgcolor: theme.palette.primary.dark } }}>
                            Take me back up ↑
                        </Button>
                    </Box>
                </Box>
            )}
        </Box>
    )
}