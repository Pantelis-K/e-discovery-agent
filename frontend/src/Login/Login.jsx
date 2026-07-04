import React, { useState } from 'react'
import { Box, Button, Card, CardContent, Container, Stack, TextField, Typography, useTheme } from '@mui/material'
import { useNavigate } from 'react-router-dom'

export default function Login({ onLogin }) {
	const navigate = useNavigate()
	const theme = useTheme()
	const { palette } = theme
	const { accent, ink, muted } = palette.brand
	const border = palette.divider
	const [email, setEmail] = useState('')
	const [password, setPassword] = useState('')

	const handleSubmit = (e) => {
		e.preventDefault()
		if (onLogin) onLogin()
		navigate('/dashboard')
	}

	return (
		<Box sx={{ minHeight: 'calc(100vh - 65px)', background: 'radial-gradient(1000px 400px at 50% -50px, #EEF1FF, #fff)', display: 'grid', placeItems: 'center' }}>
			<Container maxWidth="sm" sx={{ py: 6 }}>
				<Card elevation={0} sx={{ border: `1px solid ${border}`, borderRadius: 3, bgcolor: '#fff' }}>
					<CardContent sx={{ p: { xs: 4, md: 5 } }}>
						<Stack direction="row" spacing={1} alignItems="center" justifyContent="center" sx={{ mb: 3 }}>
							<Box sx={{ width: 26, height: 26, borderRadius: '7px', background: `linear-gradient(135deg, ${accent}, ${palette.primary.light})` }} />
							<Typography sx={{ fontWeight: 800, letterSpacing: '-0.02em', color: ink }}>FunkE</Typography>
						</Stack>
						<Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: '-0.02em', mb: 1, textAlign: 'center' }}>
							Welcome back
						</Typography>
						<Typography sx={{ color: muted, fontSize: 16, mb: 4, textAlign: 'center' }}>
							Sign in to your account to continue.
						</Typography>
						<Box component="form" onSubmit={handleSubmit}>
							<Stack spacing={2.5}>
								<TextField
									label="Email address"
									type="email"
									value={email}
									onChange={(e) => setEmail(e.target.value)}
									fullWidth
									required
								/>
								<TextField
									label="Password"
									type="password"
									value={password}
									onChange={(e) => setPassword(e.target.value)}
									fullWidth
									required
								/>
								<Button
									type="submit"
									variant="contained"
									size="large"
									disableElevation
									fullWidth
									sx={{ bgcolor: accent, borderRadius: 2, py: 1.4, '&:hover': { bgcolor: theme.palette.primary.dark } }}
								>
									Log in
								</Button>
							</Stack>
						</Box>
						<Typography sx={{ color: muted, fontSize: 14, mt: 3, textAlign: 'center' }}>
							Don't have an account?{' '}
							<Typography
								component="span"
								onClick={(e) => e.preventDefault()}
								sx={{ color: accent, fontWeight: 600, fontSize: 14, cursor: 'pointer', '&:hover': { textDecoration: 'underline' } }}
							>
								Sign up
							</Typography>
						</Typography>
					</CardContent>
				</Card>
			</Container>
		</Box>
	)
}
