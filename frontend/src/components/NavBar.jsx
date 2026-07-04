import React from 'react'
import { AppBar, Avatar, Box, Button, Container, Stack, Toolbar, Typography, useMediaQuery, useTheme } from '@mui/material'
import { useNavigate } from 'react-router-dom'

export default function NavBar({ loggedIn, onLogout }) {
    const navigate = useNavigate()
    const theme = useTheme()
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'))
    const accent = theme.palette.primary.main
    const ink = theme.palette.text.primary
    const muted = theme.palette.text.secondary
    const border = theme.palette.divider

    const handleLogout = () => {
        if (onLogout) onLogout()
        navigate('/')
    }

    return (
        <AppBar position="sticky" elevation={0} sx={{ bgcolor: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(10px)', borderBottom: `1px solid ${border}` }}>
            <Container maxWidth="lg">
                <Toolbar disableGutters sx={{ gap: 3, py: 1 }}>
                    <Stack direction="row" alignItems="center" spacing={1} onClick={() => navigate('/')} sx={{ cursor: 'pointer' }}>
                        <Box sx={{ width: 26, height: 26, background: `linear-gradient(135deg, ${accent}, ${theme.palette.primary.light})` }} />
                        <Typography sx={{ fontWeight: 800, letterSpacing: '-0.02em', color: ink }}>FunkE</Typography>
                    </Stack>

                    {!isMobile && (
                        <Stack direction="row" spacing={3} sx={{ ml: 2 }}>
                            {['Product', 'Solutions', 'Security', 'Pricing'].map((label) => (
                                <Typography
                                    key={label}
                                    sx={{
                                        color: muted,
                                        fontSize: 14,
                                        fontWeight: 500,
                                        cursor: 'pointer',
                                        '&:hover': { color: ink },
                                    }}
                                >
                                    {label}
                                </Typography>
                            ))}
                        </Stack>
                    )}

                    <Box sx={{ flexGrow: 1 }} />

                    {!loggedIn ? (
                        <>
                            <Button onClick={() => navigate('/login')} sx={{ color: ink, textTransform: 'none', fontWeight: 600 }}>
                                Log in
                            </Button>
                            <Button
                                variant="contained"
                                onClick={() => navigate('/login')}
                                disableElevation
                                sx={{
                                    bgcolor: ink,
                                    fontWeight: 600,
                                    borderRadius: 2,
                                    '&:hover': { bgcolor: theme.palette.text.primary },
                                }}
                            >
                                Get started
                            </Button>
                        </>
                    ) : (
                        <>
                            <Button onClick={() => navigate('/dashboard')} sx={{ color: ink, textTransform: 'none', fontWeight: 600 }}>
                                Dashboard
                            </Button>
                            <Button onClick={handleLogout} sx={{ color: ink, textTransform: 'none', fontWeight: 600 }}>
                                Logout
                            </Button>
                        </>
                    )}
                </Toolbar>
            </Container>
        </AppBar>
    )
}
